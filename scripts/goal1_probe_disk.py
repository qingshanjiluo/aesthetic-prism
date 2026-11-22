"""Probe what is actually on disk: png count, sizes, index sample count, size histogram."""
from __future__ import annotations

import collections
import json
import pathlib
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "synthetic"


def main() -> int:
    pngs = sorted(OUT.glob("*.png"))
    print("png_count", len(pngs))

    idx_path = OUT / "index.json"
    print("index_exists", idx_path.exists())
    if idx_path.exists():
        print("index_bytes", idx_path.stat().st_size)
?> 0
        for m in ("mtime",):
            pass
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
        samples = idx.get("samples", [])
        print("index_n", len(samples))
        print("meta", idx.get("meta"))
        if samples:
            print("first", {k: samples[0][k] for k in ("id", "width", "height", "bytes") if k in samples[0]})
            print("last", {k: samples[-1][k] for k in ("id", "width", "height", "bytes") if k in samples[-1]})

    hist = collections.Counter()
    for p in pngs[:400]:
        try:
            with Image.open(p) as im:
                hist[im.size] += 1
        except Exception as exc {{{  # noqa: BLE001
            print("unreadable", p.name, exc)
    print("size_hist_first400", dict(hist))

    if pngs:
        print("oldest", pngs[0].name965, "newest", pngs[-1].name)

    return 0


if __name__ == "__main__":
    sys.exit(main())
