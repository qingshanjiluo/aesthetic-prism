import json
import os
import sys
from pathlib import Path

ROOT = os.environ.get("AP_ROOT") or os.getcwd()
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

from aesthetic_prism.data import synthetic as syn  # noqa: E402

idx = json.loads(Path("data/synthetic/index.json").read_text(encoding="utf-8"))
samples = idx["samples"]
for s in samples[:5]:
    sid = s["id"]
    _rng, p = syn._params(sid)
    rec = syn._labels(p)
    disk = s["labels"]
    diff = {
        k: (rec.get(k), disk.get(k))
        for k in ("total", "composition", "light", "creativity", "story")
        if abs(rec.get(k, -1) - disk.get(k, -1)) > 1e-9
    }
    print(sid, "MATCH" if not diff else ("DIFF " + repr(diff)))
    if diff:
        print("   p =", {k: round(p[k], 4) for k in ("d3", "w", "g", "dL", "c", "v", "sigma", "u", "e", "L", "k", "b", "h", "r")})