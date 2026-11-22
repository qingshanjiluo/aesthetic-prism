"""Probe: how much of the frame does w actually move, vs sigma / g / h?

Reports mean |diff| AND the fraction of pixels displaced by >0.5 level, because a
mean diff can look respectable while only a few hundred pixels changed at all.
Writes nothing; prints a table.
"""
from __future__ import annotations

import os
import sys

import numpy as np
from numpy.random import PCG64, Generator

ROOT = os.environ.get("AP_ROOT") or r"G:\pipip\temp"
sys.path.insert(0, os.path.join(ROOT, "src"))

from aesthetic_prism.data import synthetic as syn  # noqa: E402


def render(sid: str, ov: dict) -> np.ndarray:
    rng, p = syn._params(sid)
    p.update(ov)
    fresh = Generator(PCG64(int(sid[-6:])))
    return np.asarray(syn._render(fresh, p), dtype=np.float32)


def main() -> None:
    ids = ["syn_000007", "syn_000123", "syn_000888", "syn_001234", "syn_001777"]
    cases = {"w": 0.20, "sigma": 4.0, "g": 0.15, "h": 0.20, "d3": 0.20}
    print(f"{chr(112)+chr(97)+chr(114)+chr(97)+chr(109):<6} {"meandiff":>9} {"changed_frac":>13} maxdiff")
    for name, delta in cases.items():
        md, fr, mx = [], [], []
        for sid in ids:
            _, p0 = syn._params(sid)
            a = render(sid, {})
            b = render(sid, {name: p0[name] + delta})
            d = np.abs(a - b)
            md.append(float(d.mean()))
            fr.append(float((d > 0.5).mean()))
            mx.append(float(d.max()))
        print(f"{name:<6} {np.mean(md):>9.3f} {np.mean(fr):>13.5f} {np.mean(mx):>7.1f}")


if __name__ == "__main__":
    main()

