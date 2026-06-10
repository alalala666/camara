"""
居家監控 - 第二步:攝影機移動偵測
原理:用背景相減偵測畫面變化,變化區域占比超過門檻 -> 視為有入侵者。

用法:
    python motion_detect.py                 # 預設參數
    python motion_detect.py --sensitivity 3 # 越小越靈敏(變化占比門檻 %)
    python motion_detect.py --no-window     # 不顯示視窗(背景執行)

操作:預覽視窗中按 q 或 Esc 離開。
偵測到入侵時會在 snapshots/ 資料夾存下截圖。
"""

import argparse
import os
import sys
import threading
import time
from datetime import datetime

import cv2

from email_notify import send_email
from recorder import record_audio

# Windows 主控台(cp950)無法顯示 ✓✗⚠ 等符號,改用 UTF-8 輸出
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


SNAPSHOT_DIR = "snapshots"
RECORDING_DIR = "recordings"
VIDEO_DIR = "videos"

# 避免同時開多個錄音(上一段還沒錄完又被觸發)
_recording_busy = threading.Lock()


def handle_intrusion(snapshot_path, ts, changed_pct, rec_seconds):
    """背景執行緒:先寄截圖信(立即),再錄音,最後寄錄音信。不阻塞主迴圈。"""
    # 1. 立即寄出截圖警報信
    send_email(
        subject="[居家安全檢測] 偵測到入侵!",
        body=f"偵測時間: {ts}\n畫面變化: {changed_pct:.1f}%\n附件為觸發當下截圖。",
        attachment_path=snapshot_path,
    )

    # 2. 錄音(若已有錄音進行中就略過,避免裝置衝突)
    wav_path = None
    if not _recording_busy.acquire(blocking=False):
        print("[錄音] 上一段錄音尚未結束,略過本次錄音")
        return
    try:
        os.makedirs(RECORDING_DIR, exist_ok=True)
        wav_path = os.path.join(
            RECORDING_DIR,
            datetime.now().strftime("audio_%Y%m%d_%H%M%S.wav"),
        )
        print(f"[錄音] 開始錄音 {rec_seconds} 秒 ...")
        record_audio(wav_path, rec_seconds)
        print(f"[錄音] ✓ 完成: {wav_path}")
    except Exception as e:
        print(f"[錄音] ✗ 錄音失敗: {e}")
        wav_path = None
    finally:
        _recording_busy.release()

    # 錄音僅存檔到 recordings/,暫不寄出


def main() -> int:
    parser = argparse.ArgumentParser(description="攝影機移動偵測")
    parser.add_argument("--camera-index", type=int, default=0, help="攝影機 index")
    parser.add_argument("--sensitivity", type=float, default=2.0,
                        help="觸發門檻:變化區域占畫面百分比(越小越靈敏),預設 2.0")
    parser.add_argument("--min-area", type=int, default=500,
                        help="忽略小於此像素面積的變化(過濾雜訊),預設 500")
    parser.add_argument("--cooldown", type=float, default=3.0,
                        help="兩次警報的最短間隔秒數,避免連續觸發,預設 3.0")
    parser.add_argument("--warmup", type=int, default=30,
                        help="啟動後先學習背景的影格數,期間不報警,預設 30")
    parser.add_argument("--no-window", action="store_true", help="不顯示預覽視窗")
    parser.add_argument("--no-save", action="store_true", help="不存截圖")
    parser.add_argument("--no-email", action="store_true",
                        help="關閉 Email 通知(預設開啟,偵測到入侵會寄信)")
    parser.add_argument("--email-cooldown", type=float, default=20.0,
                        help="兩封 Email 的最短間隔秒數,避免狂寄,預設 20")
    parser.add_argument("--no-video", action="store_true",
                        help="關閉入侵錄影(預設開啟)")
    parser.add_argument("--video-seconds", type=float, default=20.0,
                        help="入侵時錄影秒數,預設 20")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.camera_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print(f"✗ 無法開啟攝影機 index={args.camera_index}")
        return 1

    if not args.no_save:
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)

    # MOG2 背景相減器:會持續學習背景,移動物體會被標成前景
    backsub = cv2.createBackgroundSubtractorMOG2(
        history=500, varThreshold=40, detectShadows=True
    )

    print("移動偵測啟動中... (按 q 或 Esc 離開)")
    print(f"觸發門檻={args.sensitivity}%  最小面積={args.min_area}px  冷卻={args.cooldown}s")

    # 錄影用的影格率(DSHOW 有時讀不到,給合理預設)
    rec_fps = cap.get(cv2.CAP_PROP_FPS)
    if not rec_fps or rec_fps <= 0 or rec_fps > 60:
        rec_fps = 20.0

    frame_count = 0
    last_alert = 0.0
    last_email = 0.0
    video_writer = None   # 正在錄影時為 VideoWriter,否則 None
    video_end = 0.0       # 錄影結束的時間點

    while True:
        ok, frame = cap.read()
        if not ok:
            print("✗ 讀取畫面失敗")
            break
        frame_count += 1

        # 前景遮罩
        fgmask = backsub.apply(frame)
        # 去掉陰影(127)只留實體前景(255),再做形態學去雜訊
        _, fgmask = cv2.threshold(fgmask, 200, 255, cv2.THRESH_BINARY)
        fgmask = cv2.medianBlur(fgmask, 5)
        fgmask = cv2.dilate(fgmask, None, iterations=2)

        # 找出變化區塊
        contours, _ = cv2.findContours(
            fgmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        total_area = frame.shape[0] * frame.shape[1]
        changed_area = 0
        boxes = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < args.min_area:
                continue
            changed_area += area
            boxes.append(cv2.boundingRect(c))

        changed_pct = (changed_area / total_area) * 100.0

        # 暖機期間只學背景,不報警
        warming = frame_count <= args.warmup
        triggered = (not warming) and (changed_pct >= args.sensitivity)

        if triggered and (time.time() - last_alert) >= args.cooldown:
            last_alert = time.time()
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{ts}] ⚠ 偵測到移動! 變化={changed_pct:.1f}%")
            email_on = not args.no_email
            saved_path = None
            if not args.no_save or email_on:
                # 即使 --no-save,也需要檔案當附件,故一律先寫出
                saved_path = os.path.join(
                    SNAPSHOT_DIR,
                    datetime.now().strftime("motion_%Y%m%d_%H%M%S_%f.jpg"),
                )
                # 存原始畫面(不含標記框)
                cv2.imwrite(saved_path, frame)
                if not args.no_save:
                    print(f"          已存檔: {saved_path}")

            # 寄信 + 錄音都丟到背景執行緒,避免阻塞攝影機畫面(獨立冷卻)
            if email_on and (time.time() - last_email) >= args.email_cooldown:
                last_email = time.time()
                worker = threading.Thread(
                    target=handle_intrusion,
                    args=(saved_path, ts, changed_pct, args.email_cooldown),
                    daemon=True,
                )
                worker.start()

            # 開始錄影(若尚未在錄影才開新檔;一段結束後若仍有動靜會再開下一段)
            if not args.no_video and video_writer is None:
                os.makedirs(VIDEO_DIR, exist_ok=True)
                vpath = os.path.join(
                    VIDEO_DIR,
                    datetime.now().strftime("video_%Y%m%d_%H%M%S.mp4"),
                )
                h, w = frame.shape[:2]
                video_writer = cv2.VideoWriter(
                    vpath, cv2.VideoWriter_fourcc(*"mp4v"), rec_fps, (w, h)
                )
                video_end = time.time() + args.video_seconds
                print(f"          開始錄影 {args.video_seconds:.0f} 秒 -> {vpath}")

        # 錄影中:寫入當前(未標記)畫面,時間到就收檔
        if video_writer is not None:
            video_writer.write(frame)
            if time.time() >= video_end:
                video_writer.release()
                video_writer = None
                print("          ✓ 錄影完成")

        if not args.no_window:
            # 在預覽畫面上標記變化區塊
            for (x, y, w, h) in boxes:
                color = (0, 0, 255) if triggered else (0, 255, 0)
                cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            status = "WARMING UP" if warming else (
                "INTRUDER!" if triggered else "monitoring"
            )
            cv2.putText(frame, f"{status}  change={changed_pct:.1f}%",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0, 0, 255) if triggered else (0, 255, 0), 2)
            cv2.imshow("Motion Detection (press q to quit)", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break

    if video_writer is not None:
        video_writer.release()  # 收掉中途未完成的錄影
    cap.release()
    cv2.destroyAllWindows()
    print("已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
