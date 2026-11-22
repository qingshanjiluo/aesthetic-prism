from __future__ import annotations

import hashlib
import io as _io
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image

from aesthetic_prism.data import synthetic as syn

OUT = ROOT / "data" / "synthetic"
PROBE = 24


def sha_of(sid):
    rng, p = syn._params(sid)
    arr = syn._render(rng, p)
    buf = _io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, format="PNG", optimize=False)
    return hashlib.sha256(buf.getvalue()).hexdigest(), p["size"]


def main():
    idx = json.loads((OUT / "index.json").read_text(encoding="utf-8"))
    samples = idx["samples"]
    step = max(1, len(samples) // PROBE)
    picks = samples[::step][:PROBE]
    ok = 0
    bad = []
    for s in picks:
        got, size = sha_of(s["id"])
        if got == s.get("image_sha256") and size == s.get("width"):
            ok += 1
        else:
            bad.append((s["id"], s.get("width"), size))
    print("index_n", len(samples), "probe", len(picks), "match", ok, "mismatch", len(bad))
    for b in bad[:8]:
        print("MISMATCH", b)
    return 0 if not bad else 2


if __name__ == "__main__":
    sys.exit(main())
