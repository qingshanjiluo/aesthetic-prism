"""位置敏感特征的可恢复性测试。

前一次测试用 64x64 + 4x4 网格特征，对 224 画布上的主体位置差异（约 5px @64）不敏感，
导致 composition R2 为负。本脚本改用 112x112 输入 + 8x8 网格 + 前景质心
（真正的位置敏感特征），检验 composition 是否能从像素恢复。
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

AP_ROOT = os.environ.get("AP_ROOT") or os.getcwd()
sys.path.insert(0, os.path.join(AP_ROOT, "src"))
os.chdir(AP_ROOT)

import numpy as np
from PIL import Image

from aesthetic_prism.data import synthetic as syn

N = 300


def feats_rich(sample: dict) -> np.ndarray:
    a = np.asarray(
        Image.open(sample["image_path"]).convert("RGB").resize((112, 112), Image.BILINEAR),
        dtype=np.float32,
    ) / 255.0
    g = a.mean(2)
    grid = [g[int(i * 14):int((i + 1) * 14), int(j * 14):int((j + 1) * 14)].mean()
            for i in range(8) for j in range(8)]
    med = float(np.median(g))
    w = np.abs(g - med)
    tot = float(w.sum()) + 1e-9
    yy, xx = np.mgrid[0:112, 0:112]
    cx = float((xx * w).sum()) / tot / 112.0
    cy = float((yy * w).sum()) / tot / 112.0
    lw = float(w[:, :56].sum()) / tot
    rw = float(w[:, 56:].sum()) / tot
    tw = float(w[:56, :].sum()) / tot
    bw = float(w[56:, :].sum()) / tot
    return np.array(grid + [cx, cy, lw, rw, tw, bw, float(g.mean()), float(g.std())])


def knn_r2(X: np.ndarray, Y: np.ndarray, k: int = 10) -> tuple[float, float]:
    mu, sd = X.mean(0), X.std(0) + 1e-9
    A = (X - mu) / sd
    d2 = ((A[:, None, :] - A[None, :, :]) ** 2).sum(2)
    np.fill_diagonal(d2, np.inf)
    idx = np.argsort(d2, axis=1)[:, :k]
    pred = Y[idx].mean(1)
    r2 = 1 - ((Y - pred) ** 2).sum() / ((Y - Y.mean()) ** 2).sum()
    return float(r2), float(np.abs(Y - pred).mean())


GETTERS = {
    "composition": lambda p: 100 * (0.55 * p["d3"] + 0.25 * (1 - abs(p["w"] - 0.5) * 2) + 0.20 * (1 - abs(p["g"] - 0.35) / 0.35)),
    "composition_only_d3": lambda p: 100 * p["d3"],
    "composition_only_w": lambda p: 100 * (1 - abs(p["w"] - 0.5) * 2),
    "creativity": lambda p: 100 * (0.50 * p["u"] + 0.30 * p["e"] + 0.20 * min(p["L"], 3) / 3),
    "creativity_only_u": lambda p: 100 * p["u"],
    "light": lambda p: 100 * (0.40 * (1 - p["dL"]) + 0.30 * (1 - abs(p["c"] - 1.1) / 0.5) + 0.20 * (1 - p["v"] / 0.8) + 0.10 * (1 - p["sigma"] / 12)),
    "story": lambda p: 100 * (0.40 * min(int(p["k"]), 6) / 6 + 0.25 * int(p["b"]) + 0.20 * p["h"] + 0.15 * min(int(p["r"]), 3) / 3),
    "raw_d3": lambda p: float(p["d3"]),
    "raw_w": lambda p: float(p["w"]),
    "raw_g": lambda p: float(p["g"]),
    "raw_u": lambda p: float(p["u"]),
    "raw_e": lambda p: float(p["e"]),
    "raw_dL": lambda p: float(p["dL"]),
    "raw_sigma": lambda p: float(p["sigma"]),
}


def main():
    samples = json.loads(pathlib.Path("data/synthetic/index.json").read_text(encoding="utf-8"))["samples"][:N]
    X = np.array([feats_rich(s) for s in samples])
    print(f"n={len(X)} feat_dim={X.shape[1]}", flush=True)

    out = {"n": len(X), "feature": "112px + 8x8 grid + foreground centroid", "k": 10, "results": {}}
    for name, getter in GETTERS.items():
        Y = np.array([getter(syn._params(s["id"])[1]) for s in samples])
        r2, mae = knn_r2(X, Y)
        out["results"][name] = {"r2": round(r2, 4), "mae": round(mae, 3), "std": round(float(Y.std()), 2)}
        print(f"  {name:22s} R2={r2:7.3f}  MAE={mae:6.2f}  std={Y.std():5.2f}", flush=True)

    pathlib.Path("reports/position_sensitive_probe.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nwrote reports/position_sensitive_probe.json")


if __name__ == "__main__":
    main()
