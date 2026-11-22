"""Measure the residual-vs-e relation after e became TRAIL STRENGTH.

For each id: render at three seeds with sigma=0 (isolates the trail channel), report
the frame std; then force e over a gridceiling and re-measure, so the gate can be
calibrated on the OBSERVED slope instead of a guessed one.

ASCII only. Read-only on the repo; prints a table.
"""
from __future__ import annotations

import os
import sys

import numpy as np
from numpy.random import PCG64, Generator

ROOT = os.environ.get("AP_ROOT") or r"G:\\pipip\\temp"
sys.path.insert(0, os.path.join(ROOT, "src"))

from aesthetic_prism.data import synthetic as syn  # noqa: E402

IDS = [
    "syn_000007",
    "syn_000123",
    "syn_000888",
    "syn_001234",
    "syn_001777",
]
SEEDS = (0, 12345, 987654321)
GRID = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


def frame(p: dict, seed: int) -> np.ndarray:
    dev = Generator(PCG64(seed))
    return np.asarray(syn._render(dev, dict(p)), dtype=np.float32)


def resid(p: dict) -> float:
    st = np.stack([frame(p, s) for s in SEEDS])
    return float(st.std(axis=0).mean())


def main() -> None:
    print("sid          size   e_in    resid   r_sub")
    for sid in IDS:
        _, p0 = syn._params(sid)
        p = dict(p0)
        p["sigma"] = 0.0
        for e in GRID:
            q = dict(p)
            q["e"] = e
            print(f"{sid}  {p['size']:>4}  {e:<5.2f}  {resid(q):>7.4f}  {syn._r_sub(q):>7.3f}")
    print("--- done ---")


if __name__ == "__main__":
    main()
