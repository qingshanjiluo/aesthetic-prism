# -*- coding: utf-8 -*-
"""Aesthetic Prism launcher - one menu for the whole workspace.

Contract (desktop-launcher-kit):
  P0  every core action reachable from one command: python launcher.py <action>
      long jobs stream progress; settings live in one external file (CFG);
      failures print a readable reason; state is queryable.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "Aesthetic Prism"
APP_DESC = "\u56fe\u7247\u5ba1\u7f8e\u8bc4\u5206\u5de5\u4f5c\u53f0"
PORT = 8000

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("AP_ROOT") or HERE).resolve()
SRC = ROOT / "src"
PYPROJECT = ROOT / "pyproject.toml"
REPORTS = ROOT / "reports"
LOGS = ROOT / "logs"
QA = ROOT / "qa"
UPLOADS = ROOT / "data" / "uploads"
SYNTHETIC = ROOT / "data" / "synthetic"
CHECKPOINTS = ROOT / "checkpoints"
CONFIG_DIR = ROOT / "configs"
INDEX_JSON = SYNTHETIC / "index.json"
GATE_LOG = ROOT / "GATE_LOG.md"
BASE = REPORTS / "teacher_student_mae.json"
PY = sys.executable
CFG = str(CONFIG_DIR / "launcher.json")
CFG_DEFAULTS = {
    "port": PORT,
    "host": "127.0.0.1",
    "mock_on_test": True,
    "open_ui_after_serve": True,
    "gate_log_tail": 60,
}


def _enable_vt() -> bool:
    if os.name != "nt":
        return bool(sys.stdout.isatty())
    if os.environ.get("NO_COLOR"):
        return False
    try:
        import ctypes

        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not k.GetConsoleMode(h, ctypes.byref(mode)):
            return False
        return bool(k.SetConsoleMode(h, mode.value | 0x0004))
    except Exception:
        return False


COLOR = _enable_vt()


def c(text: str, code: str) -> str:
    if not COLOR:
        return text
    return "\x1b[" + code + "m" + text + "\x1b[0m"


def dim(t: str) -> str:
    return c(t, "2")


def bold(t: str) -> str:
    return c(t, "1")


def ok(t: str) -> str:
    return c("OK  " + t, "32")


def warn(t: str) -> str:
    return c("??  " + t, "33")


def bad(t: str) -> str:
    return c("XX  " + t, "31")


def acc(t: str) -> str:
    return c(t, "36")


def dwidth(s: str) -> int:
    n = 0
    for ch in s:
        if unicodedata.combining(ch):
            continue
        n += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return n


def dpad(s: str, width: int) -> str:
    return s + " " * max(0, width - dwidth(s))


def line(ch: str, width: int = 62) -> None:
    print(ch * width)


def title(text: str) -> None:
    print()
    line("=")
    print("  " + bold(text))
    line("=")


def set_title(text: str) -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleTitleW(ctypes.c_wchar_p(text))
    except Exception:
        pass


def ask(prompt: str) -> str:
    try:
        return input(prompt)
    except EOFError:
        return ""


def run(cmd, cwd=None, env_extra=None) -> int:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(SRC)
    env["AP_ROOT"] = str(ROOT)
    if env_extra:
        env.update(env_extra)
    print(dim("  $ " + " ".join(str(x) for x in cmd)))
    try:
        p = subprocess.Popen(cmd, cwd=str(cwd or ROOT), env=env)
    except FileNotFoundError:
        print(bad("command not found: " + str(cmd[0])))
        return 127
    except PermissionError:
        print(bad("not executable: " + str(cmd[0])))
        return 126
    rc = p.wait()
    print(ok("done rc=0") if rc == 0 else bad("failed rc=" + str(rc)))
    return rc


def port_up(port: int = PORT) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.4)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def api(path: str, timeout: float = 3.0):
    url = "http://127.0.0.1:" + str(PORT) + path
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def parse_val(raw):
    if isinstance(raw, (bool, int, float)):
        return raw
    s = str(raw or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('', ""):
        s = s[1:-1]
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if s.startswith("[") and s.endswith("]"):
        body = s[1:-1].strip()
        if not body:
            return []
        return [parse_val(p) for p in body.split(",") if p.strip()]
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


def load_cfg() -> dict:
    cfg = dict(CFG_DEFAULTS)
    try:
        p = Path(CFG)
        if not p.is_file():
            return cfg
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return cfg
    if isinstance(data, dict):
        cfg.update(data)
    return cfg


def save_cfg(cfg: dict) -> bool:
    path = Path(CFG)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file():
            Path(str(path) + ".bak").write_bytes(path.read_bytes())
        tmp = path.with_suffix(path.suffix + ".tmp")
        text = json.dumps(cfg, ensure_ascii=False, indent=2) + chr(10)
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
        return True
    except Exception:
        return False


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def cfg_snapshot() -> dict:
    cfg = load_cfg()
    return {
        "cfg": CFG,
        "cfg_exists": Path(CFG).is_file(),
        "port": cfg.get("port", PORT),
        "host": cfg.get("host", "127.0.0.1"),
        "mock_on_test": cfg.get("mock_on_test"),
        "open_ui_after_serve": cfg.get("open_ui_after_serve"),
        "gate_log_tail": cfg.get("gate_log_tail"),
        "root": str(ROOT),
        "src": str(SRC),
        "python": PY,
    }


def dataset_count():
    idx = read_json(INDEX_JSON)
    if isinstance(idx, dict):
        items = idx.get("items")
        if isinstance(items, list):
            return len(items)
        n = idx.get("n")
        if isinstance(n, int):
            return n
    if SYNTHETIC.is_dir():
        return len([f for f in SYNTHETIC.iterdir() if f.suffix.lower() == ".png"])
    return 0


def checkpoint_rows():
    rows = []
    if not CHECKPOINTS.is_dir():
        return rows
    for p in sorted(CHECKPOINTS.rglob("*.pt")):
        if p.is_file():
            rows.append((str(p.relative_to(ROOT)), p.stat().st_size))
    return rows


def onnx_paths() -> list:
    out = []
    for base in (ROOT / "artifacts", ROOT / "models"):
        if base.is_dir():
            for p in sorted(base.rglob("*.onnx")):
                out.append((str(p.relative_to(ROOT)), p.stat().st_size))
    return out


def stale_procs() -> list:
    rows = []
    try:
        import subprocess as sp

        out = sp.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=20,
        )
        data = json.loads(out.stdout or "[]")
        if isinstance(data, dict):
            data = [data]
    except Exception:
        return rows
    for item in data:
        if not isinstance(item, dict):
            continue
        cl = item.get("CommandLine") or ""
        if "aesthetic_prism.serve" not in cl:
            continue
        rows.append((int(item.get("ProcessId") or 0), str(item.get("Name") or ""), cl))
    return rows


def act_status() -> int:
    title("STATUS")
    snap = cfg_snapshot()
    port = int(snap.get("port") or PORT)
    up = port_up(port)
    print(dpad("  service", 16) + (ok("up on port " + str(port)) if up else warn("down")))
    print(dpad("  dataset", 16) + str(dataset_count()) + dim(" png"))
    ncfg = len(list(CONFIG_DIR.glob("*.toml"))) if CONFIG_DIR.is_dir() else 0
    print(dpad("  configs", 16) + str(ncfg))
    print(dpad("  onnx", 16) + str(len(onnx_paths())))
    print(dpad("  checkpoints", 16) + str(len(checkpoint_rows())))
    nrep = len(list(REPORTS.glob("*.json"))) if REPORTS.is_dir() else 0
    print(dpad("  reports", 16) + str(nrep))
    sp = stale_procs()
    print(dpad("  stale", 16) + (str(len(sp)) if sp else dim("none")))
    print(dpad("  cfg file", 16) + (dim(str(CFG)) if snap.get("cfg_exists") else dim("absent -> defaults")))
    return 0


def _env_mock(enable: bool) -> dict:
    return {"AP_MODE": "mock"} if enable else {}


def act_serve() -> int:
    title("SERVE")
    cfg = load_cfg()
    port = int(cfg.get("port") or PORT)
    host = str(cfg.get("host") or "127.0.0.1")
    if port_up(port):
        print(warn("already listening on " + host + ":" + str(port)))
        if cfg.get("open_ui_after_serve"):
            webbrowser.open("http://" + host + ":" + str(port) + "/")
        return 0
    print(dim("  starting uvicorn " + host + ":" + str(port)))
    rc = run(
        [PY, "-X", "utf8", "-m", "uvicorn",
         "--app-dir", str(SRC),
         "aesthetic_prism.serve.app:app",
         "--host", host, "--port", str(port)],
    )
    return rc


def act_stop() -> int:
    title("STOP")
    rows = stale_procs()
    if not rows:
        print(dim("  no uvicorn worker for aesthetic_prism.serve"))
        return 0
    for pid, name, cl in rows:
        print(dpad("  " + str(pid), 8) + name)
        rc = run(["taskkill", "/PID", str(pid), "/T", "/F"])
        if rc != 0:
            print(warn("  pid " + str(pid) + " rc=" + str(rc)))
    left = stale_procs()
    if not left:
        print(ok("  stopped"))
    else:
        print(warn("  still alive: " + str(len(left))))
    return 0 if not left else 1


def act_open_ui() -> int:
    cfg = load_cfg()
    host = str(cfg.get("host") or "127.0.0.1")
    port = int(cfg.get("port") or PORT)
    url = "http://" + host + ":" + str(port) + "/"
    print(acc(url))
    webbrowser.open(url)
    return 0


def act_open_logs() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    print(acc(str(LOGS)))
    if os.name == "nt":
        run(["explorer", str(LOGS)])
    return 0


def act_open_dir() -> int:
    print(acc(str(ROOT)))
    if os.name == "nt":
        run(["explorer", str(ROOT)])
    return 0


def _imgs_under(p: Path) -> list:
    exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    if p.is_file() and p.suffix.lower() in exts:
        return [p]
    if p.is_dir():
        return [f for f in sorted(p.iterdir()) if f.suffix.lower() in exts]
    return []


def act_score() -> int:
    title("SCORE")
    raw = ask("  image or dir [" + str(UPLOADS) + "]: ").strip().strip(chr(34))
    target = Path(raw) if raw else UPLOADS
    imgs = _imgs_under(target)
    if not imgs:
        print(bad("no image under " + str(target)))
        return 2
    rc = run([PY, "-X", "utf8", "-m", "aesthetic_prism.score"] + [str(i) for i in imgs])
    return rc


def act_selfcheck() -> int:
    title("SELF-CHECK")
    fails = 0
    ncfg = len(list(CONFIG_DIR.glob("*.toml"))) if CONFIG_DIR.is_dir() else 0
    checks = [
        ("python", Path(PY).is_file() or shutil.which(str(PY)) is not None),
        ("pyproject", PYPROJECT.is_file()),
        ("src", SRC.is_dir()),
        ("configs(dir)", CONFIG_DIR.is_dir()),
        ("configs(5 toml)", ncfg == 5),
        ("frontend", (ROOT / "frontend" / "index.html").is_file()),
        ("launcher.bat", (ROOT / "launcher.bat").is_file()),
    ]
    for label, good in checks:
        if good:
            print(ok(label))
        else:
            print(bad(label))
            fails += 1
    print()
    if fails == 0:
        print(ok("all green"))
    else:
        print(bad(str(fails) + " failed"))
    return 0 if fails == 0 else 1


def act_demo() -> int:
    return run([PY, "-X", "utf8", "-m", "aesthetic_prism.data.synthetic",
                "--n", "200", "--seed", "42", "--out", str(SYNTHETIC)],
               env_extra={"AP_MODE": "mock"})


def act_reproduce() -> int:
    return run([PY, "-X", "utf8", "-m", "aesthetic_prism.distill",
                "--source", str(INDEX_JSON)],
               env_extra={"AP_MODE": "mock"})


def act_tests() -> int:
    return run([PY, "-X", "utf8", "-m", "pytest", "-q"],
               env_extra={"AP_MODE": "mock"})


def act_lint() -> int:
    return run([PY, "-X", "utf8", "-m", "ruff", "check", "src", "tests"])


def act_typecheck() -> int:
    return run([PY, "-X", "utf8", "-m", "mypy", "src"])


def act_coverage() -> int:
    return run([PY, "-X", "utf8", "-m", "pytest", "-q", "--cov=aesthetic_prism"],
               env_extra={"AP_MODE": "mock"})



def act_checkenv() -> int:
    import platform

    title("ENV")
    print(dpad("  python", 16) + platform.python_version())
    print(dpad("  exe", 16) + PY)
    print(dpad("  platform", 16) + platform.platform())
    for mod in ("torch", "onnxruntime", "fastapi", "uvicorn", "pytest", "PIL", "numpy"):
        try:
            m = __import__(mod)
        except Exception as exc:
            print(dpad("  " + mod, 16) + bad(type(exc).__name__))
            continue
        ver = getattr(m, "__version__", "?")
        print(dpad("  " + mod, 16) + ok(str(ver)))
    return 0


def act_health() -> int:
    title("HEALTH")
    port = int(load_cfg().get("port") or PORT)
    if not port_up(port):
        print(warn("service down - run serve first"))
        return 1
    data = api("/healthz")
    if data is None:
        print(bad("/healthz no response"))
        return 1
    print(ok("/healthz"))
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def act_learn() -> int:
    title("LEARN")
    rows = [
        ("serve", "start the FastAPI service on PORT"),
        ("stop", "kill the uvicorn worker for this project"),
        ("score", "score one image or a whole directory"),
        ("demo", "regenerate the 200-sample synthetic set (seed 42)"),
        ("reproduce", "rerun distillation against data/synthetic/index.json"),
        ("tests", "pytest -q with AP_MODE=mock"),
        ("lint", "ruff check src tests"),
        ("typecheck", "mypy src"),
        ("coverage", "pytest with --cov=aesthetic_prism"),
        ("status", "ports, dataset, artifacts, stale workers"),
        ("selfcheck", "verify file layout and toolchain"),
        ("gate_log", "append one line to GATE_LOG.md"),
    ]
    for k, v in rows:
        print(dpad("  " + k, 14) + dim(v))
    return 0


def act_log() -> int:
    title("GATE_LOG")
    if not Path(GATE_LOG).is_file():
        print(warn("GATE_LOG.md missing"))
        return 1
    lines = Path(GATE_LOG).read_text(encoding="utf-8-sig").splitlines()
    n = int(load_cfg().get("gate_log_tail") or 60)
    print(dim("  " + str(len(lines)) + " lines, tail " + str(n)))
    for ln in lines[-n:]:
        print("  " + ln)
    return 0


def act_gate_log() -> int:
    title("GATE_LOG APPEND")
    msg = ask("  entry: ").strip()
    if not msg:
        print(warn("empty - nothing appended"))
        return 2
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(GATE_LOG, "a", encoding="utf-8") as fh:
        fh.write("- " + stamp + " " + msg + chr(10))
    print(ok("appended"))
    return 0



def act_search() -> int:
    title("SEARCH")
    pat = ask("  pattern: ").strip()
    if not pat:
        print(warn("empty"))
        return 2
    hits = 0
    for base in (SRC, Path(ROOT) / "tests", Path(ROOT) / "scripts"):
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*.py")):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, ln in enumerate(text.splitlines(), 1):
                if pat in ln:
                    print("  " + str(f) + ":" + str(i) + " " + ln.strip())
                    hits += 1
    print()
    if hits:
        print(ok(str(hits) + " hit(s)"))
    else:
        print(warn("0 hit"))
    return 0 if hits else 1


def act_maintain() -> int:
    title("MAINTAIN")
    n = 0
    for f in Path(ROOT).rglob("*"):
        if not f.is_file():
            continue
        if f.suffix in (".py", ".ts", ".js", ".md", ".toml", ".json", ".bat", ".html", ".css", ".ico", ".txt"):
            continue
        if f.suffix in (".pyc", ".log", ".tmp", ".bak", ".bak1", ".bakdal"):
            print("  " + str(f))
            n += 1
    print()
    print(ok(str(n) + " candidate(s)"))
    return 0


def act_load() -> int:
    title("LOAD")
    cmd = ["locust", "-f", "tests/load/locustfile.py", "--headless",
           "-u", "8", "-t", "30s", "--csv", "reports/load"]
    return run(cmd, cwd=ROOT)


def act_export() -> int:
    title("EXPORT")
    src = Path(ROOT) / "artifacts" / "student_int8.onnx"
    if not src.is_file():
        print(bad("artifacts/student_int8.onnx missing"))
        return 1
    dst = REPORTS / "student_int8.onnx"
    REPORTS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(ok(str(dst)))
    return 0


def act_fill() -> int:
    title("FILL")
    cfg = load_cfg()
    cfg["port"] = PORT
    if not save_cfg(cfg):
        return 1
    print(ok("configs/launcher.json -> defaults"))
    return 0


def act_help() -> int:
    title("HELP")
    print("  launcher.py <subcommand>    run one action, then exit")
    print("  launcher.py                interactive menu")
    print()
    print(dim("  subcommands:"))
    for k, _n, _f in MENU:
        print(dpad("  " + k, 14) + dim(_f.__name__))
    return 0



MENU = [
    ("1", "serve", act_serve),
    ("2", "stop", act_stop),
    ("3", "score", act_score),
    ("4", "demo", act_demo),
    ("5", "reproduce", act_reproduce),
    ("6", "status", act_status),
    ("7", "selfcheck", act_selfcheck),
    ("8", "open ui", act_open_ui),
    ("9", "open dir", act_open_dir),
    ("c", "config", act_cfg),
    ("l", "log", act_log),
    ("t", "tests", act_tests),
    ("k", "lint", act_lint),
    ("y", "typecheck", act_typecheck),
    ("v", "coverage", act_coverage),
    ("d", "check env", act_checkenv),
    ("h", "help", act_help),
    ("g", "gate log", act_gate_log),
    ("o", "open logs", act_open_logs),
    ("e", "export", act_export),
    ("f", "fill cfg", act_fill),
    ("s", "search", act_search),
    ("m", "maintain", act_maintain),
    ("w", "load", act_load),
    ("x", "health", act_health),
    ("n", "learn", act_learn),
    ("q", "quit", None),
]

GROUPS = [
    ("SERVICE", ["1", "2", "8"]),
    ("CHECK", ["3", "4", "5", "6", "7", "x", "w"]),
    ("BUILD", ["t", "k", "y", "v", "e", "f"]),
    ("TOOL", ["c", "l", "g", "o", "d", "h", "n", "s", "m", "9"]),
]


def render_menu() -> None:
    idx = {k: (k, name) for k, name, _f in MENU}
    for gname, keys in GROUPS:
        print()
        print(acc(bold("  " + gname)))
        for k in keys:
            item = idx.get(k)
            if item is None:
                continue
            print("   " + warn("[" + k + "]") + " " + item[1])
    print()
    print(dim("  q  quit"))
    print()


def _dispatch(key: str) -> int:
    for k, _name, fn in MENU:
        if k == key:
            if fn is None:
                return 0
            return int(fn() or 0)
    print(warn("  unknown key: " + key))
    return 2


def main(argv: list) -> int:
    set_title(APP_NAME)
    if len(argv) > 0:
        want = str(argv[0]).strip()
        for k, _name, fn in MENU:
            if k == want and fn is not None:
                return int(fn() or 0)
        print(warn("unknown subcommand: " + want))
        return 2
    while True:
        print()
        print(acc(bold("  " + APP_NAME)) + dim("  " + APP_DESC))
        render_menu()
        key = ask("  > ").strip()
        if key in ("", "q", "quit", "exit"):
            return 0
        rc = _dispatch(key)
        print()
        print(dim("  rc=" + str(rc)))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

