# 审查截图：CDP 驱动 headless Chrome，登录页 + 各视图 × 1440/1024/768/390
import base64, json, subprocess, sys, time, urllib.request
from pathlib import Path
import websocket

BASE = "http://127.0.0.1:8005"
OUT = Path(__file__).resolve().parent.parent / "docs" / "review-shots"
OUT.mkdir(parents=True, exist_ok=True)
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEBUG_PORT = 9333

chrome = subprocess.Popen([
    CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
    f"--remote-debugging-port={DEBUG_PORT}",
    "--remote-allow-origins=*",
    "--window-size=1440,900", "about:blank",
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def wait_ws():
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json") as r:
                tabs = json.load(r)
            for t in tabs:
                if t.get("type") == "page":
                    return t["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("CDP not up")

class CDP:
    def __init__(self, url):
        self.ws = websocket.create_connection(url, timeout=60)
        self.mid = 0
    def cmd(self, method, **params):
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.mid:
                return msg.get("result", msg)
    def shot(self, name):
        r = self.cmd("Page.captureScreenshot", format="png")
        (OUT / name).write_bytes(base64.b64decode(r["data"]))
        print("shot", name, flush=True)

try:
    c = CDP(wait_ws())
    c.cmd("Page.enable")
    c.cmd("Runtime.enable")
    sizes = [(1440,900),(1024,768),(768,1024),(390,844)]
    views = ["home","library","compare","annotate","wallet"]
    for w,h in sizes:
        c.cmd("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=(w<500))
        c.cmd("Page.navigate", url=BASE + "/")
        time.sleep(2.5)
        c.shot(f"login-{w}.png")
        c.cmd("Runtime.evaluate", expression="document.getElementById('login-view').hidden=true;")
        time.sleep(0.4)
        for v in views:
            c.cmd("Runtime.evaluate", expression=f"document.querySelector('#app-tabs .tab[data-view=\"{v}\"]').click();")
            time.sleep(0.8)
            c.shot(f"{v}-{w}.png")
    print("SHOTS_DONE")
finally:
    chrome.terminate()
    try: chrome.wait(timeout=5)
    except Exception: chrome.kill()
