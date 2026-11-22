"""Calibrate the A1b2 trend gate: per-id rho and endpoint ratio. Read-only, ASCII."""
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
E_GRID = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


def frame(p, seed):
    return np.asarray(syn._render(Generator(PCG64(seed)), dict(p)), dtype=np.float32)


def resid(p):
    st = np.stack([frame(p, s) for s in SEEDS])
    return float(st.std(axis=0).mean())


def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    out = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for t in range(i, j + 1):
            out[order[t]] = avg
        i = j + 1
    return out


def rho(xa, xb):
    ra, rb = ranks(list(xa)), ranks(list(xb))
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    num = sum((a - ma) * (b - mb) for a, b in zip(ra, rb))
    da = sum((a - ma) ** 2 for a in ra) ** 0.5
    db = sum((b - mb) ** 2 for b in rb) ** 0.5
    return 0.0 if da == 0.0 or db == 0.0 else num / (da * db)


def main():
    print("sid          rho       end_ratio   resid_e1    worst_below")
    grid = tuple(float(i) for i in range(len(E_GRID)))
    rows = []
    for sid in IDS:
        _, p0 = syn._params(sid)
        rs = []
        for e in E_GRID:
            q = dict(p0)
            q["sigma"] = 0.0
            q["e"] = e
            rs.append(resid(q))
        r = rho(grid, rs)
        ratio = rs[-1] / max(rs[:-1])
        rows.append((sid, r, ratio, rs[-1], max(rs[:-1])))
        print(f"{sid}  {r:>8.4f}  {ratio:>10.4f}  {rs[-1]:>9.4f}  {max(rs[:-1]):>10.4f}")
    print("---")
    print("min_rho      ", round(min(x[1] for x in rows), 4))
    print("min_end_ratio", round(min(x[2] for x in rows), 4))
    print("mean_rho     ", round(float(np.mean([x[1] for x in rows])), 4))
    print("mean_ratio   ", round(float(np.mean([x[2] for x in rows])), 4))


if __name__ == "__main__":
    main()
