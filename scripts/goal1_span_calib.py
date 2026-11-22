"""Per-id span(e) = resid(e)/resid(1) table, to locate the collapse region."""
from __future__ import annotations

import os
import sys

import numpy as np
from numpy.random import PCG64, Generator

ROOT = os.environ.get("AP_ROOT")
sys.path.insert(0, os.path.join(ROOT, "src"))

from aesthetic_prism.data import synthetic as syn

IDS = ["syn_000007", "syn_000123", "syn_000888", "syn_001234", "syn_001777"]
SEEDS = (0, 12345, 987654321)
E_GRID = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)

def frame(p, seed):
    return np.asarray(syn._render(Generator(PCG64(seed)), dict(p)), dtype=np.float32)

def resid(p):
    st = np.stack([frame(p, s) for s in SEEDS])
    return float(st.std(axis=0).mean())

def main():
    print("sid          " + " ".join(f"{e:>6.2f}" for e in E_GRID))
    for sid in IDS:
        _, p0 = syn._params(sid)
        rs = []
        for e in E_GRID:
            q = dict(p0)
            q["sigma"] = 0.0
            q["e"] = e
            rs.append(resid(q))
        sp = [v / rs[-1] for v in rs]
        print(f"{sid}  " + " ".join(f"{v:>6.3f}" for v in sp))

if __name__ == "__main__":
    main()
