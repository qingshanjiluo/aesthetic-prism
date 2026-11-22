"""分布覆盖诊断：验证集是否落在训练集支撑集之外（数据覆盖不足 ⇒ 泛化 gap 结构性）。

若 val→train 的最近邻距离 ≈ train→train 的最近邻距离，则两者同分布，
泛化 gap 只能来自模型（过拟合/容量/训练）。若 val 明显更远，则训练数据覆盖不足。
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

from aesthetic_prism.data.schema import split_of


def thumb(path: str, size: int = 16) -> np.ndarray:
    return np.asarray(
        Image.open(path).convert("RGB").resize((size, size), Image.BILINEAR),
        dtype=np.float32,
    ).reshape(-1) / 255.0


def nn_dist(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1))


def main():
    samples = json.loads(pathlib.Path("data/synthetic/index.json").read_text(encoding="utf-8"))["samples"]
    tr = [s for s in samples if split_of(s["id"]) == "train"][:200]
    va = [s for s in samples if split_of(s["id"]) == "val"][:60]
    te = [s for s in samples if split_of(s["id"]) == "test"][:60]

    T = np.array([thumb(s["image_path"]) for s in tr])
    V = np.array([thumb(s["image_path"]) for s in va])
    E = np.array([thumb(s["image_path"]) for s in te])

    d_vt = nn_dist(V, T).min(1)
    d_et = nn_dist(E, T).min(1)
    D_tt = nn_dist(T, T)
    np.fill_diagonal(D_tt, np.inf)
    d_tt = D_tt.min(1)

    out = {
        "n_train": len(T),
        "n_val": len(V),
        "n_test": len(E),
        "val_to_train": {"mean": round(float(d_vt.mean()), 4),
                         "p50": round(float(np.percentile(d_vt, 50)), 4),
                         "p95": round(float(np.percentile(d_vt, 95)), 4)},
        "test_to_train": {"mean": round(float(d_et.mean()), 4),
                          "p50": round(float(np.percentile(d_et, 50)), 4),
                          "p95": round(float(np.percentile(d_et, 95)), 4)},
        "train_to_train": {"mean": round(float(d_tt.mean()), 4),
                           "p50": round(float(np.percentile(d_tt, 50)), 4),
                           "p95": round(float(np.percentile(d_tt, 95)), 4)},
        "ratio_val": round(float(d_vt.mean() / d_tt.mean()), 3),
        "ratio_test": round(float(d_et.mean() / d_tt.mean()), 3),
    }
    print(json.dumps(out, indent=2))
    pathlib.Path("reports/coverage_probe.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
