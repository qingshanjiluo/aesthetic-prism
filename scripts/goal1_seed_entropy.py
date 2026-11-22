"""A1: is the render path residual rng entropy LABEL-SCALED or FREE?

The renderer still calls rng by design (jitter tracked by e, kind gated by u,
gaussian noise scaled by sigma). The defect would be entropy whose MAGNITUDE no
label governs, i.e. a fixed floor that adds texture without changing semantics.

Test, per sample id:
  outs = [ _render(Generator(PCG64(s)), p) for s in SEEDS ]
  resid = st.std(axis=0).mean()   ~ the seed-determined part of the frame
sigma is the only label that scales pixel entropy by construction, so A1 reduces to:
  A1a  resid strictly increasing in sigma
  A1b  resid at sigma=0 is 0   (geometry fully determined by p)
"""
from __future__ import annotations

import os
import sys

import numpy as np
from numpy.random import PCG64, Generator

ROOT = os.environ.get("AP_ROOT") or r"G:\\pipip\\temp"
sys.path.insert(0, os.path.join(ROOT, "src"))

from aesthetic_prism.data import synthetic as syn  # noqa: E402

IDS = ["syn_000007", "syn_000123", "syn_000888", "syn_001234", "syn_001777"]
SEEDS = (0, 12345, 987654321)
SIGMAS = (0.0, 3.0, 6.0, 12.0)


def frame(p: dict, seed: int) -> np.ndarray:
    return np.asarray(syn._render(Generator(PCG64(seed)), dict(p)), dtype=np.float32)


def main() -> None:
    print("sigma   pooled_resid_sd")
    rows = []
    for sg in SIGMAS:
        vals = []
        for sid in IDS:
            _, p0 = syn._params(sid)
            p = dict(p0)
            p["sigma"] = sg
            st = np.stack([frame(p, s) for s in SEEDS])
            vals.append(float(st.std(axis=0).mean()))
        rows.append((sg, float(np.mean(vals))))

    ok = True
    prev = -1.0
    for sg, sd in rows:
        print(f"{sg:<7.1f}{sd:>10.5f}")
        if sd <= prev:
            ok = False
        prev = sd
    print("---")
    print(f"A1a resid_strictly_increases : {"PASS" if ok else "FAIL"}")
    print(f"A1b resid_zero_at_sigma0    : {"PASS" if rows[0][1] < 1e-6 else "FAIL"} ({rows[0][1]:.6f})")
    raise SystemExit(0 if ok and rows[0][1] < 1e-6 else 1)


if __name__ == "__main__":
    main()

