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


def _enable_vt() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not k.GetConsoleMode(h, ctypes.byref(mode)):
            return
        k.SetConsoleMode(h, mode.value | 4)
    except Exception:
        pass


_enable_vt()


def c(code: str, text: str) -> str:
    return chr(27) + "[" + str(code) + "m" + str(text) + chr(27) + "[0m"


def dim(text) -> str:
    return c("2", text)


def bold(text) -> str:
    return c("1", text)


def ok(text) -> str:
    return c("32", text)


def warn(text) -> str:
    return c("33", text)


def bad(text) -> str:
    return c("31", text)


def acc(text) -> str:
    return c("36", text)



ANSI_RE = "\\x1b\\[[0-9;]*m"


def _strip_ansi(s: str) -> str:
    import re

    return re.sub(ANSI_RE, "", s)


def dwidth(s: str) -> int:
    s = _strip_ansi(str(s))
    n = 0
    for ch in s:
        n += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return n


def dpad(s: str, width: int) -> str:
    s = str(s)
    vis = dwidth(s)
    if vis >= width:
        return s
    return s + " " * (width - vis)


def line(ch: str = "-", n: int = 64) -> str:
    return ch * n


def title(text: str) -> None:
    print()
    pad = max(0, 58 - dwidth(text))
    print(acc(bold("  == " + text + " " + "=" * pad)))
    print()


def set_title(text: str) -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleTitleW(ctypes.c_wchar_p(str(text)))
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


def api(path: str, timeout: float = 5.0):
    cfg = load_cfg()
    host = str(cfg.get("host") or "127.0.0.1")
    port = int(cfg.get("port") or PORT)
    url = "http://" + host + ":" + str(port) + path
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def parse_val(raw: str):
    s = str(raw).strip()
    if s == "":
        return ""
    if s in ("true", "True", "on", "yes"):
        return True
    if s in ("false", "False", "off", "no"):
        return False
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [parse_val(p) for p in inner.split(",")]
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def load_cfg() -> dict:
    cfg = dict(CFG_DEFAULTS)
    p = Path(CFG)
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            data = {}
        if isinstance(data, dict):
            for k in CFG_DEFAULTS:
                if k in data:
                    cfg[k] = data[k]
        cfg["cfg_exists"] = True
    else:
        cfg["cfg_exists"] = False
    return cfg


def save_cfg(cfg: dict) -> bool:
    data = {k: v for k, v in cfg.items() if k in CFG_DEFAULTS}
    try:
        p = Path(CFG)
        p.parent.mkdir(parents=True, exist_ok=True)
        bak = Path(str(CFG) + ".bak")
        if p.is_file():
            shutil.copy2(str(p), str(bak))
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    except Exception as exc:
        print(bad("save_cfg failed: " + repr(exc)))
        return False
    return True



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


def _imgs_under(folder: Path) -> list:
    exts = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
    if not folder.is_dir():
        return []
    return sorted([p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exts])


def act_score() -> int:
    uploads = _imgs_under(UPLOADS)
    if not uploads:
        print(warn("  no images in " + str(UPLOADS)))
        return 1
    for i, p in enumerate(uploads):
        print("   [" + str(i + 1) + "] " + p.name + "  " + str(p.stat().st_size) + " B")
    pick = ask("  index (default 1): ").strip() or "1"
    try:
        idx = int(pick) - 1
    except ValueError:
        print(bad("  not a number: " + pick))
        return 2
    if idx < 0 or idx >= len(uploads):
        print(bad("  out of range: " + pick))
        return 2
    img = uploads[idx]
    cmd = [sys.executable, "-X", "utf8", "-m", "aesthetic_prism.score", str(img)]
    print(dim("  " + " ".join(cmd)))
    rc, out, err = run(cmd, cwd=str(ROOT), env_extra={"AP_ROOT": str(ROOT)})
    if out:
        print(out.rstrip())
    if err:
        print(bad(err.rstrip()))
    return int(rc)


def act_selfcheck() -> int:
    checks = [
        ("python", sys.executable),
        ("pyproject", str(PYPROJECT)),
        ("src", str(SRC)),
        ("configs data", str(CONFIG_DIR / "data" / "data.yaml")),
        ("configs model", str(CONFIG_DIR / "model" / "model.yaml")),
        ("configs train", str(CONFIG_DIR / "train" / "train.yaml")),
        ("configs serve", str(CONFIG_DIR / "serve" / "serve.yaml")),
        ("configs repro", str(CONFIG_DIR / "repro" / "repro_constants.txt")),
        ("frontend", str(HERE / "frontend" / "index.html")),
        ("launcher.bat", str(HERE / "launcher.bat")),
        ("app.ico", str(HERE / "app.ico")),
    ]
    failed = 0
    for name, path in checks:
        good = Path(path).exists()
        if not good:
            failed += 1
        tag = ok("[ok] ") if good else bad("[--] ")
        print(tag + str(name))
    print()
    if failed == 0:
        print(ok("  all " + str(len(checks)) + " checks passed"))
    else:
        print(bad("  " + str(failed) + " failed"))
    return 0 if failed == 0 else 1



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



def act_cfg() -> int:
    title("CONFIG")
    print(dim("  file " + str(CFG)))
    cfg = load_cfg()
    print(dim("  existing " + str(bool(cfg.get("cfg_exists")))))
    for k in sorted(CFG_DEFAULTS.keys()):
        cur = cfg.get(k, CFG_DEFAULTS[k])
        dflt = CFG_DEFAULTS[k]
        tail = ""
        if cur != dflt:
            tail = dim("  (default " + repr(dflt) + ")")
        print(dpad("  " + k, 22) + repr(cur) + tail)
    return 0


def act_set_cfg() -> int:
    title("CONFIG SET")
    key = ask("  key: ").strip()
    if key not in CFG_DEFAULTS:
        print(warn("unknown key: " + key))
        print(dim("  known: " + ", ".join(sorted(CFG_DEFAULTS))))
        return 2
    val = parse_val(ask("  value: "))
    cfg = load_cfg()
    cfg.pop("cfg_exists", None)
    cfg[key] = val
    if not save_cfg(cfg):
        return 1
    print(ok(key + " = " + repr(val)))
    return 0



def act_quit() -> int:
    return 0


MENU = [
    ("1", "启动服务", act_serve),
    ("2", "停止服务", act_stop),
    ("3", "运行评分", act_score),
    ("4", "演示", act_demo),
    ("5", "复现流水线", act_reproduce),
    ("6", "状态", act_status),
    ("7", "自检", act_selfcheck),
    ("8", "打开网页", act_open_ui),
    ("9", "打开目录", act_open_dir),
    ("c", "配置", act_cfg),
    ("l", "日志", act_log),
    ("t", "测试", act_tests),
    ("k", "代码检查", act_lint),
    ("y", "类型检查", act_typecheck),
    ("v", "覆盖率", act_coverage),
    ("d", "检查环境", act_checkenv),
    ("h", "帮助", act_help),
    ("g", "门禁日志", act_gate_log),
    ("o", "打开日志", act_open_logs),
    ("e", "导出", act_export),
    ("f", "补全配置", act_fill),
    ("s", "搜索", act_search),
    ("m", "维护", act_maintain),
    ("w", "加载", act_load),
    ("x", "健康检查", act_health),
    ("n", "学习", act_learn),
    ("q", "退出", act_quit),
]

GROUPS = [
    ("服务", ["1", "2", "8", "9", "o"]),
    ("检查", ["3", "4", "5", "6", "7", "x", "w", "m"]),
    ("构建", ["t", "k", "y", "v", "e", "f"]),
    ("工具", ["c", "l", "g", "d", "h", "n", "s", "q"]),
]


def _status_line() -> str:
    port = int(load_cfg().get("port") or PORT)
    if port_up(port):
        return ok("  " + chr(9679) + " service up") + dim("  :" + str(port))
    return warn("  " + chr(9675) + " service down") + dim("  :" + str(port))


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
    print(dim("  q)") + " " + dim("退出"))
    print()


def _dispatch(key: str) -> int:
    for k, _name, fn in MENU:
        if k == key:
            return int(fn() or 0)
    print(warn("  unknown key: " + key))
    return 2


def main(argv: list) -> int:
    set_title(APP_NAME)
    if len(argv) > 0:
        want = str(argv[0]).strip()
        for k, _name, fn in MENU:
            if k == want:
                return int(fn() or 0)
        print(warn("unknown subcommand: " + want))
        return 2
    while True:
        print()
        print(acc(bold("  " + APP_NAME)) + dim("  " + APP_DESC))
        print(_status_line())
        render_menu()
        key = ask("  > ").strip()
        if key in ("", "q", "quit", "exit"):
            return 0
        rc = _dispatch(key)
        print()
        print(dim("  rc=" + str(rc)))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

