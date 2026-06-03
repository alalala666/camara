"""
居家監控 - 第一步:裝置測試
測試攝影機與麥克風是否可以正常存取。

用法:
    python test_devices.py            # 兩者都測
    python test_devices.py --camera   # 只測攝影機
    python test_devices.py --mic      # 只測麥克風
"""

import argparse
import sys
from typing import Optional

# Windows 主控台(cp950)無法顯示 ✓✗⚠ 等符號,改用 UTF-8 輸出
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def test_camera(index: int = 0, show_window: bool = True) -> bool:
    """嘗試開啟攝影機並抓取畫面。"""
    try:
        import cv2
    except ImportError:
        print("[攝影機] ✗ 缺少 opencv-python,請執行: pip install opencv-python")
        return False

    print(f"[攝影機] 嘗試開啟裝置 index={index} ...")
    # Windows 用 CAP_DSHOW 開啟較快且穩定
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print(f"[攝影機] ✗ 無法開啟裝置 index={index}(可能被佔用或不存在)")
        return False

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"[攝影機] ✓ 開啟成功  解析度={width}x{height}  FPS={fps:.1f}")

    ok, frame = cap.read()
    if not ok or frame is None:
        print("[攝影機] ✗ 開啟成功但讀不到畫面")
        cap.release()
        return False

    print("[攝影機] ✓ 成功讀取畫面")

    if show_window:
        print("[攝影機] 顯示預覽中,按 q 或 Esc 關閉視窗 ...")
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            cv2.imshow("Camera Test (press q to quit)", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):  # q or Esc
                break
        cv2.destroyAllWindows()

    cap.release()
    return True


def list_microphones() -> None:
    import sounddevice as sd

    print("[麥克風] 可用的輸入裝置:")
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            mark = " (預設)" if i == sd.default.device[0] else ""
            print(f"   [{i}] {dev['name']}  channels={dev['max_input_channels']}{mark}")


def test_microphone(duration: float = 3.0, device: Optional[int] = None) -> bool:
    """錄製數秒音訊並回報音量,確認麥克風有收到聲音。"""
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError:
        print("[麥克風] ✗ 缺少 sounddevice,請執行: pip install sounddevice")
        return False

    try:
        list_microphones()
    except Exception as e:
        print(f"[麥克風] ✗ 無法列出裝置: {e}")
        return False

    samplerate = 44100
    print(f"[麥克風] 開始錄音 {duration} 秒,請對著麥克風說話 ...")
    try:
        recording = sd.rec(
            int(duration * samplerate),
            samplerate=samplerate,
            channels=1,
            device=device,
            dtype="float32",
        )
        sd.wait()
    except Exception as e:
        print(f"[麥克風] ✗ 錄音失敗: {e}")
        return False

    rms = float(np.sqrt(np.mean(recording**2)))
    peak = float(np.max(np.abs(recording)))
    print(f"[麥克風] ✓ 錄音完成  RMS={rms:.5f}  峰值={peak:.5f}")

    # 簡單音量條
    bars = int(min(rms * 200, 40))
    print("[麥克風] 音量: [" + "#" * bars + "-" * (40 - bars) + "]")

    if peak < 0.001:
        print("[麥克風] ⚠ 幾乎沒有收到聲音,請確認麥克風未靜音/權限是否開啟")
        return False

    print("[麥克風] ✓ 有偵測到聲音,麥克風正常")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="居家監控裝置測試")
    parser.add_argument("--camera", action="store_true", help="只測攝影機")
    parser.add_argument("--mic", action="store_true", help="只測麥克風")
    parser.add_argument("--camera-index", type=int, default=0, help="攝影機 index")
    parser.add_argument("--no-window", action="store_true", help="不顯示攝影機預覽視窗")
    parser.add_argument("--mic-seconds", type=float, default=3.0, help="麥克風錄音秒數")
    args = parser.parse_args()

    # 沒指定就兩者都測
    run_cam = args.camera or not (args.camera or args.mic)
    run_mic = args.mic or not (args.camera or args.mic)

    results = {}
    if run_cam:
        print("=" * 50)
        results["攝影機"] = test_camera(args.camera_index, show_window=not args.no_window)
    if run_mic:
        print("=" * 50)
        results["麥克風"] = test_microphone(args.mic_seconds)

    print("=" * 50)
    print("測試結果:")
    for name, ok in results.items():
        print(f"   {name}: {'✓ 正常' if ok else '✗ 失敗'}")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
