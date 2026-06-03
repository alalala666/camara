"""
居家監控 - Email 通知模組
偵測到入侵時寄送 Email(可附截圖)。預設用 Gmail SMTP。

== 設定方式(環境變數) ==
為了安全,帳密不寫在程式裡,改從環境變數讀取。
PowerShell 設定(只在當前視窗有效):
    $env:EMAIL_USER = "你的gmail@gmail.com"
    $env:EMAIL_PASS = "應用程式密碼(16碼,不是登入密碼)"
    $env:EMAIL_TO   = "收件人@example.com"   # 不設則寄給自己

Gmail 需先開啟兩步驟驗證,並到下列網址產生「應用程式密碼」:
    https://myaccount.google.com/apppasswords

== 測試 ==
    python email_notify.py        # 寄一封測試信
"""

import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from typing import Optional

# Windows 主控台(cp950)無法顯示 ✓✗⚠ 等符號,改用 UTF-8 輸出
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


PASSWORD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "password.txt")


def _load_password_file() -> dict:
    """從 password.txt 讀取設定(第1行=信箱, 第2行=應用程式密碼, 第3行=收件人,可省略)。"""
    if not os.path.exists(PASSWORD_FILE):
        return {}
    with open(PASSWORD_FILE, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    cfg = {}
    if len(lines) >= 1:
        cfg["user"] = lines[0]
    if len(lines) >= 2:
        # 應用程式密碼可能含空格,移除後再用
        cfg["password"] = lines[1].replace(" ", "")
    if len(lines) >= 3:
        cfg["to"] = lines[2]
    return cfg


def get_config() -> dict:
    """讀取寄信設定。優先用環境變數,缺少時改讀 password.txt。"""
    file_cfg = _load_password_file()
    user = os.environ.get("EMAIL_USER") or file_cfg.get("user")
    password = os.environ.get("EMAIL_PASS") or file_cfg.get("password")
    to = os.environ.get("EMAIL_TO") or file_cfg.get("to") or user
    return {
        "host": os.environ.get("EMAIL_HOST", "smtp.gmail.com"),
        "port": int(os.environ.get("EMAIL_PORT", "587")),
        "user": user,
        "password": password,
        "to": to,
    }


def send_email(
    subject: str,
    body: str,
    attachment_path: Optional[str] = None,
    cfg: Optional[dict] = None,
) -> bool:
    """寄送一封 Email,可選擇附加一張圖片。回傳是否成功。"""
    cfg = cfg or get_config()

    if not cfg["user"] or not cfg["password"]:
        print("[Email] ✗ 未設定 EMAIL_USER / EMAIL_PASS 環境變數,無法寄信")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["user"]
    msg["To"] = cfg["to"]
    msg.set_content(body)

    # 附加截圖
    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            data = f.read()
        filename = os.path.basename(attachment_path)
        msg.add_attachment(
            data, maintype="image", subtype="jpeg", filename=filename
        )

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as server:
            server.starttls(context=context)
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
        print(f"[Email] ✓ 已寄出 -> {cfg['to']}")
        return True
    except Exception as e:
        print(f"[Email] ✗ 寄信失敗: {e}")
        return False


if __name__ == "__main__":
    from datetime import datetime

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ok = send_email(
        subject="[居家監控] 測試信件",
        body=f"這是一封測試信,寄出時間 {ts}。\n若你收到代表 Email 通知設定成功。",
    )
    raise SystemExit(0 if ok else 1)
