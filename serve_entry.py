# Aesthetic Prism 桌面入口：起本地 uvicorn 服务 + 打开默认浏览器（登录页）
# 用于 PyInstaller 打包（--onefile）或源码直接运行。
# 双击 exe / python serve_entry.py → 端口探测（8000 被占自动 fallback 8010）→ 开 http://127.0.0.1:PORT/
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# 端口优先级：AP_PORT env > 8000 空闲 > 8010 空闲 > 8000 强制
PORTS = [int(os.environ.get("AP_PORT", "0"))] if os.environ.get("AP_PORT") else [8000, 8010, 8001]
HOST = os.environ.get("AP_HOST", "127.0.0.1")
# PyInstaller 解包资源在 sys._MEIPASS；源码运行用脚本所在目录
_mei = getattr(sys, "_MEIPASS", None)
ROOT = Path(_mei) if _mei else Path(__file__).resolve().parent

# 确保 cwd 指向资源根
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def _port_free(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            s.connect(("127.0.0.1", port))
        return False  # 连上了 = 被占
    except (ConnectionRefusedError, OSError):
        return True    # 拒绝连接 = 空闲


def pick_port() -> int:
    for p in PORTS:
        if _port_free(p):
            return p
    # 全被占：用 env 指定的或 8000（uvicorn 会报错，至少明确）
    return PORTS[0]


def open_browser_later(port: int) -> None:
    time.sleep(1.5)
    try:
        webbrowser.open(f"http://{HOST}:{port}/")
    except Exception:
        pass


def main() -> int:
    port = pick_port()
    print(f"[aesthetic-prism] using port {port} (candidates: {PORTS})", flush=True)
    threading.Thread(target=open_browser_later, args=(port,), daemon=True).start()

    # 日志落盘：data/serve.log（追加，不覆盖历史）
    log_dir = ROOT / "data"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = open(log_dir / "serve.log", "a", encoding="utf-8", buffering=1)

    cmd = [
        sys.executable, "-m", "uvicorn",
        "aesthetic_prism.serve.app:app",
        "--host", HOST, "--port", str(port),
        "--app-dir", str(ROOT / "src"),
        "--log-level", "info",
    ]
    try:
        subprocess.call(cmd, cwd=str(ROOT), stdout=log_file, stderr=subprocess.STDOUT)
    except KeyboardInterrupt:
        pass
    finally:
        log_file.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
