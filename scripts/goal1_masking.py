"""Diagnostic: is the label signal masked by non-label random factors?"""
from __future__ import annotations

import os
import sys

import numpy as np
from numpy.random import PCG64, Generator

ROOT = os.environ.get("AP_ROOT") or r"G:\皮皮\编程项目\aesthetic-prism"
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from aesthetic_prism.data import synthetic as syn

IDS = ["syn_000007", "syn_000123", "syn_000888", "syn_001234", "syn_001777"]
KEYS = {
    "d3": 0.20, "w": 0.20, "g": 0.15,
    "dL": 0.15, "c": 0.20, "v": 0.20, "sigma": 4.0,
    "u": 0.20, "e": 0.20, "h": 0.20,
}


def render(sid, ov=None):
    rng = Generator(PCG64(int(sid[-6:])))
    _r, p = syn._params(sid)
    if ov:
        p = dict(p)
        p.update(ov)
    return np.asarray(syn._render(rng, p), dtype=np.float32)


def d(a, b):
    return float(np.abs(a - b).mean())


def main():
    lab = {k: [] for k in KEYS}
    dup = []
    th = []
    h1 = []
    for sid in IDS:
        base = render(sid)
        dup.append(d(base, render(sid)))
        for k, delta in KEYS.items():
            _r, p0 = syn._params(sid)
            lab[k].append(d(base, render(sid, {k: p0[k] + delta})))
        th.append(d(base, render(sid, {"theta": 0.60})))
        h1.append(d(base, render(sid, {"h1": 0.35})))
    print("dup baseline mean = %.4f" % float(np.mean(dup)))
    print("--- label params ---")
    for k in KEYS:
        print("  %-6s delta=%-6s meandiff=%.3f" % (k, KEYS[k], float(np.mean(lab[k]))))
    print("--- non-label params ---")
    print("  theta  delta=0.60   meandiff=%.3f" % float(np.mean(th)))
    print("  h1     delta=0.35   meandiff=%.3f" % float(np.mean(h1)))
    s = float(np.mean([np.mean(lab[k]) for k in KEYS]))
    n = (float(np.mean(th)) + float(np.mean(h1))) / 2.0
    print()
    print("mean label-param delta   S = %.3f" % s)
    print("mean non-label  delta   N = %.3f" % n)
    print("S / N = %.3f" % (s / max(n, 1e-9)))


if __name__ == "__main__":
    main()
