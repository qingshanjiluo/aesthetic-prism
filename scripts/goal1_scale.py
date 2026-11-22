"""尺度诊断：标签信号主要存在于哪个空间尺度？

把每张图降采样到不同分辨率，用 4x4 网格特征做 kNN 预测标签，看 R2/MAE 随分辨率变化。
  - 低分辨率就能预测 -> 信号在全局结构，GAP 之后应保留 -> 缺口在优化
  - 只有高分辨率能预测 -> 信号在细节，14x14 + GAP 会丢失 -> 缺口在架构
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

DIMS = ("composition", "light", "creativity", "story")


def feats_at(path: str, size: int) -> np.ndarray:
    a = np.asarray(
        Image.open(path).convert("RGB").resize((size, size), Image.BILINEAR),
        dtype=np.float32,
    ) / 255.0
    g = a.mean(2)
    grid = max(1, size // 4)
    f = [float(g[i * grid:(i + 1) * grid, j * grid:(j + 1) * grid].mean())
         for i in range(4) for j in range(4)]
    return np.array(f + [float(a.mean()), float(a.std())], dtype=np.float64)


def knn_eval(X: np.ndarray, Y: np.ndarray, is_tr: np.ndarray, k: int = 10) -> tuple[float, float]:
    mu, sd = X[is_tr].mean(0), X[is_tr].std(0) + 1e-9
    A = (X[is_tr] - mu) / sd
    B = (X[~is_tr] - mu) / sd
    d2 = ((B[:, None, :] - A[None, :, :]) ** 2).sum(2)
    idx = np.argsort(d2, axis=1)[:, :k]
    pred = Y[is_tr][idx].mean(1)
    yt = Y[~is_tr]
    r2 = 1 - ((yt - pred) ** 2).sum() / ((yt - yt.mean()) ** 2).sum()
    return float(r2), float(np.abs(yt - pred).mean())


def main():
    samples = json.loads(pathlib.Path("data/synthetic/index.json").read_text(encoding="utf-8"))["samples"]
    labels = np.array([[float(s["labels"][d]) for d in DIMS] for s in samples])
    is_tr = np.array([split_of(s["id"]) == "train" for s in samples])

    out = {"n_train": int(is_tr.sum()), "n_eval": int((~is_tr).sum()), "by_size": {}}
    print(f"train={int(is_tr.sum())} eval={int((~is_tr).sum())}")
    print(f"{'size':>6} " + " ".join(f"{d[:5]:>7}" for d in DIMS) + f" {'mae4':>7}")
    for size in (8, 16, 32, 64, 112, 224):
        X = np.array([feats_at(s["image_path"], size) for s in samples])
        maes = []
        for di in range(4):
            _, mae = knn_eval(X, labels[:, di], is_tr, k=10)
            maes.append(mae)
        out["by_size"][str(size)] = {DIMS[di]: round(maes[di], 3) for di in range(4)}
        out["by_size"][str(size)]["mae4"] = round(float(np.mean(maes)), 3)
        print(f"{size:>6} " + " ".join(f"{maes[di]:7.5}" for di in range(4)) + f" {np.mean(maes):7.3f}")

    pathlib.Path("reports/scale_probe.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nwrote reports/scale_probe.json")


if __name__ == "__main__":
    main()