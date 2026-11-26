# 冒烟脚本：起服务 → 打 7 个端点 → 杀进程。AP_PORT 指定端口（缺省 8001）。
import os, socket, subprocess, sys, time, json, urllib.request

PORT = int(os.environ.get("AP_PORT", "8001"))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

def port_free(p):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3); s.connect(("127.0.0.1", p))
        return False
    except OSError:
        return True

if not port_free(PORT):
    print(f"FAIL: port {PORT} busy"); sys.exit(1)

env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
p = subprocess.Popen([sys.executable, "-m", "uvicorn", "aesthetic_prism.serve.app:app",
                      "--host", "127.0.0.1", "--port", str(PORT), "--app-dir", str(ROOT / "src")],
                     env=env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
                if r.status == 200: break
        except Exception:
            continue
    else:
        print("FAIL: /health not up after 20s"); p.kill(); sys.exit(1)
    print("health OK")

    checks = [
        ("GET /assets", f"http://127.0.0.1:{PORT}/assets?limit=1", {}),
        ("GET /annotations", f"http://127.0.0.1:{PORT}/annotations?limit=1", {}),
        ("GET /annotations/export", f"http://127.0.0.1:{PORT}/annotations/export?fmt=csv", {}),
    ]
    for name, url, _ in checks:
        with urllib.request.urlopen(url, timeout=5) as r:
            assert r.status == 200, f"{name} -> {r.status}"
        print(f"{name} 200")

    # POST /annotations（单机无 token 放行）
    body = json.dumps({"path": "uploads/_smoke.jpg", "composition": 5, "light": 5,
                       "creativity": 5, "story": 5, "quality": "可用", "annotator": "smoke"}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/annotations", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        d = json.loads(r.read()); assert d["total"] == 5.0, d
    print("POST /annotations 200 total=5.0")

    # 清理
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/annotations?path=uploads/_smoke.jpg", method="DELETE")
    with urllib.request.urlopen(req, timeout=5) as r:
        assert json.loads(r.read())["deleted"] == 1
    print("DELETE /annotations cleaned")

    print("SMOKE_PASS")
finally:
    p.terminate()
    try:
        p.wait(timeout=5)
    except Exception:
        p.kill()
