"""Gate A1 (unreachable randomness) / A3 (weight-effect rank agreement).

A1: once _params has returned, NOTHING in the render path may consume rng.
    Render the same param dict with three different generator seeds and require
    byte-identical output. This is the property the earlier probe was missing --
    perturbing a DERIVED value (theta/h1/h2) changing pixels is correct and
    desirable, it just means pi xels track d3/e; the defect would be pixel
    entropy that no label explains, which A1 catches directly.

A3: Spearman between a param's weight in _labels and its measured pixel effect.
    Sampled params only; sigma is compared at its own scale.
"""
from __future__ import annotations

import os
import sys

import numpy as np
from numpy.random import PCG64, Generator

ROOT = os.environ.get("AP_ROOT") or r"G:\pipip\temp"
sys.path.insert(0, os.path.join(ROOT, "src"))

from aesthetic_prism.data import synthetic as syn  # noqa: E402

IDS = ["syn_000007", "syn_000123", "syn_000888", "syn_001234", "syn_001777"]

CASES = [
    ("d3", 0.20, 0.55),
    ("w", 0.20, 0.25),
    ("g", 0.15, 0.20),
    ("dL", 0.15, 0.40),
    ("c", 0.20, 0.30),
    ("v", 0.20, 0.20),
    ("sigma", 4.0, 0.10),
    ("u", 0.20, 0.50),
    ("e", 0.20, 0.30),
    ("h", 0.20, 0.20),
]

SEEDS = (0, 12345, 987654321)


def render(sid: str, ov: dict, seed: int = 0, p_in: dict | None = None) -> np.ndarray:
    p = dict(syn._params(sid)[1]) if p_in is None else dict(p_in)
    p.update(ov)
    return np.asarray(syn._render(Generator(PCG64(seed)), p), dtype=np.uint8)


def effect(name: str, delta: float) -> float:
    vals = []
    for sid in IDS:
        _, p0 = syn._params(sid)
        a = render(sid, {})
        b = render(sid, {name: p0[name] + delta})
        vals.append(float(np.abs(a.astype(np.float32) - b.astype(np.float32)).mean()))
    return float(np.mean(vals))


def ranks(v: list[float]) -> list[float]:
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for t in range(i, j + 1):
            r[order[t]] = avg
        i = j + 1
    return r


def spearman(x: list[float], y: list[float]) -> float:
    rx, ry = np.array(ranks(x)), np.array(ranks(y))
    mx, my = rx.mean(), ry.mean()
    sx = float(np.sqrt(np.sum((rx - mx) ** 2)))
    sy = float(np.sqrt(np.sum((ry - my) ** 2)))
    return float(np.sum((rx - mx) * (ry - my)) / max(sx * sy, 1e-12))


def main() -> None:
    # A1: renderer must be a pure function of the param dict
    a1_bad = []
    for sid in IDS:
        outs = [render(sid, {}, seed=s) for s in SEEDS]
        same = all(np.array_equal(outs[0], o) for o in outs[1:])
        print(f"A1 {sid} seed_independent={same} (False == byte-identical, PASS)")
        if not same:
            a1_bad.append(sid)

    # ADevice3
    print("param   delta  weight   effect")
    ws, es, a3_bad = [], [], []
    for name, delta, wgt in CASES:
        e = effect(name, delta)
        ws.append(wgt)
        es.append(e)
        print(f"{name:<7}{delta:>6.2f}{wgt:>8.2f}{e:>9.3f}")
        if e <= 0.0:
            a3_bad.append(name)
    rho = spearman(ws, es)
    print("---")
    print(f"A1 seed_independent_render : {'PASS' if not a1_bad else 'FAIL'}")
    print(f"A3 all_params_reach_pixels : {'PASS' if not a3_bad else 'FAIL'} ({a3_bad})")
    print(f"A3 spearman_weight_effect  : {rho:+.4f} {'PASS' if rho >= 0.55 else 'FAIL'}")
    ok = not a1_bad and not a3_bad and rho >= 0.55
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
