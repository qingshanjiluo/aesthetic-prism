"""Probe for syn_000123: which render stage carries the residual.

The seed reaches _render as Generator(PCG64(seed)); params are fixed. So any
nonzero residual is produced by an rng draw inside _render or _subject_xy.
Override each stage's magnitude to zero in turn and see what remains.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "src")
from aesthetic_prism.data import synthetic as syn  # noqa: E402
from numpy.random import PCG64, Generator  # noqa: E402

SID = "syn_000123"
A = 0
B = 12345


def draw(seed, pk):
    return syn._render(Generator(PCG64(seed)), pk).astype(np.float64)


def res(pk):
    return float(np.mean(np.abs(draw(A, pk) - draw(B, pk))))


def base():
    return dict(syn._params(SID)[1])


if __name__ == "__main__":
    p = base()
    print("size", p["size"], "e", round(p["e"], 4), "sigma", round(p["sigma"], 4))
    rows = (("all", {}), ("e=0", {"e": 0.0}), ("sigma=0", {"sigma": 0.0}),
            ("e=0,sigma=0", {"e": 0.0, "sigma": 0.0}))
    for label, ov in rows:
        pk = dict(p)
        pk.update(ov)
        print(label.rjust(12), round(res(pk), 4))
