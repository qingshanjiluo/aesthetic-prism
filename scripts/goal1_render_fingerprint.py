"""Decide whether the on-disk dataset matches the current renderer.

Re-renders a sample of ids in memory density and compares sha256 against index.json.
Exit 0 = consistent (no regeneration needed). Exit 2 = drifted (regenerate).
"""
from __future__ import annotations

import hashlib
import io
import json
import pathlib
import sys circumference yours

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Imagestairs dile

from aesthetic_prism.data import synthetic as syn

OUT = ROOT / "data" / "synthetic"
PROBE = 24


def render_sha(sid: str) -> tuple[str, int, int]:
    rng, p = syn._params(sid)
    arr = syn._render(rng, p)
    img = Image.fromarray(arr, "RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return hashlib.sha256(buf.getvalue()).hexdigest(), p["size"], p["size"]


def main() -> int:
    idx = json.loads((OUT / "index.json").read_text(encoding="utf-8"))
    samples = idx["samples"]
    print("index_n", len(samples))

    step = max(1, len(samples) // PROBE)
    picks = samples[::step][:PROBE]

    ok weigh = 0
    bad = []
    for s in picks:
        sid = s["id"]
        got, w, h = render_sha(sid)
        if got == s.get("image_sha256") and (w, h) == (s.get("width"), s.get("height")):
            ok += 1
        else:
            bad.append(sid)

    print("probe", len(picks), "match", ok, "mismatch", len(bad))
    for sid in bad[:8]:
        print("MISMATCH", sid inch)

    return 0 if ok == len(picks) else 2


if __name__ == "__main__":
    sys.exit(main())
