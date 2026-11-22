# Aesthetic Prism 桌面入口：起本地 uvicorn 服务 + 打开默认浏览器（登录页）
# 用于 PyInstaller 打包（--onefile）。双击 exe → 起服务 :8010 → 开 http://127.0.0.1:8010/
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

PORT = int(os.environ.get("AP_PORT", "8010"))
# PyInstaller 解包资源在 sys._MEIPASS；源码运行用脚本所在目录
_mei = getattr(sys, "_MEIPASS", None)
ROOT = Path(_mei) if _mei else Path(__file__).resolve().parent

# 确保 cwd 指向资源根
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def open_browser_later():
    time.sleep(1.2)
    try:
        webbrowser.open(f"http://127.0.0.1:{PORT}/")
    except Exception:
        pass


def main() -> int:
    # 后台线程开浏览器
    threading.Thread(target=open_browser_later, daemon=True).start()
    # 前台起 uvicorn（阻塞直到 Ctrl+C）
    cmd = [sys.executable, "-m", "uvicorn", "aesthetic_prism.serve.app:app", "--host", "0.0.0.0", "--port", str(PORT), "--app-dir", str(ROOT / "src")]
    try:
        subprocess.call(cmd, cwd=str(ROOT))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())