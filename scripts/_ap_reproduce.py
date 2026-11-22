import subprocess
import sys

PY = sys.executable
STEPS = [
    ("data_audit", [PY, "-X", "utf8", "src/aesthetic_prism/bench/data_audit.py"]),
    ("metric_recheck", [PY, "-X", "utf8", "src/aesthetic_prism/bench/metric_recheck.py"]),
    ("eval_recheck", [PY, "-X", "utf8", "src/eval.py", "--recheck", "--against", "reports/metric_recheck.json"]),
    ("pytest", [PY, "-X", "utf8", "-m", "pytest", "-q"]),
]

fails = []
for name, cmd in STEPS:
    print("=" * 20, name, "=" * 20)
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    print(out[-6000:])
    print("RC_%s=%d" % (name, r.returncode))
    if r.returncode != 0:
        fails.append(name)

print("FAILS=", fails)
sys.exit(1 if fails else 0)
