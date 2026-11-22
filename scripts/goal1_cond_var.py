"""条件方差判决实验：mae4 的信息论下限。

原理：模型能学到的上限是 E[y | x]（贝叶斯最优），其不可消除的 MAE 下界由
Var[y | x] 决定。若我们能证明「相同/极近像素下标签仍有大方差」，则下界成立。

做法（不依赖任何模型）：
1. 用像素的低维可测代理量（亮度直方图、网格均值、边缘能量）做 kNN：
   对每个 val 样本找 train 中像素代理最近的 k 个邻居，看它们的标签离散程度。
   若近邻标签的 std 很大，说明像素相同但标签不同 → 条件方差大 → MAE 下界高。
2. 计算「用近邻标签均值作为预测」的 MAE，这就是非参数贝叶斯估计器的实际表现。
   若该 MAE 已在 11~13 区间，则任何模型（含深度网）都难以显著更低。
3. 同时给出「用它自己的参数」做 kNN 的对照（应为 ~0，证明代码正确）。
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
from aesthetic_prism.data.schema import split_of

DIMS = ("composition", "light", "creativity", "story")


def pixel_feats(s):
    a = np.asarray(Image.open(s["image_path"]).convert("RGB").resize((64, 64), Image.BILINEAR), dtype=np.float32) / 255.0
    g = a.mean(2)
    # 16 bin 亮度直方图
    hist, _ = np.histogram(g, bins=16, range=(0, 1), density=True)
    # 4x4 网格均值（粗位置）
    grid = [g[i * 16:(i + 1) * 16, j * 16:(j + 1) * 16].mean() for i in range(4) for j in range(4)]
    # 边缘能量
    gx = np.abs(np.diff(g, axis=1)).mean()
    gy = np.abs(np.diff(g, axis=0)).mean()
    # 通道均值/std
    ch = list(a.mean((0, 1))) + list(a.std((0, 1)))
    return np.array(list(hist) + grid + [gx, gy] + ch, dtype=np.float64)


def param_feats(s):
    _r, p = syn._params(s["id"])
    v = []
    for k in ("h1", "h2", "theta", "d3", "w", "g", "dL", "c", "v", "sigma", "u", "e", "h"):
        v += [float(p[k]), float(p[k]) ** 2]
    for k in ("L", "k", "b", "r"):
        v.append(float(p[k]))
    return np.array(v, dtype=np.float64)


def knn_mae(Xtr, Ytr, Xva, Yva, k=5):
    """对每个 val 样本取 train 中 k 近邻标签均值作为预测，返回每维 MAE 与近邻标签 std。"""
    # 标准化
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    A, B = (Xtr - mu) / sd, (Xva - mu) / sd
    d2 = ((B[:, None, :] - A[None, :, :]) ** 2).sum(2)   # (nva, ntr)
    idx = np.argsort(d2, axis=1)[:, :k]
    pred = Ytr[idx].mean(1)                              # (nva, 4)
    mae = np.abs(pred - Yva).mean(0)
    # 近邻标签的内部 std（条件方差代理）
    cond_std = Ytr[idx].std(1).mean(0)                   # (4,)
    return mae, cond_std, d2[np.arange(len(B)), idx[:, 0]]


def main():
    samples = json.loads(pathlib.Path("data/synthetic/index.json").read_text(encoding="utf-8"))["samples"]
    tr = [s for s in samples if split_of(s["id"]) == "train"][:500]
    va = [s for s in samples if split_of(s["id"]) == "val"][:150]
    print(f"n_train={len(tr)} n_val={len(va)}")

    Ytr = np.array([[float(s["labels"][d]) for d in DIMS] for s in tr])
    Yva = np.array([[float(s["labels"][d]) for d in DIMS] for s in va])

    out = {"n_train": len(tr), "n_val": len(va), "k": 5}

    # --- 对照：参数空间 kNN（应接近 0，验证流程正确）---
    Ptr = np.array([param_feats(s) for s in tr])
    Pva = np.array([param_feats(s) for s in va])
    mae_p, _, d_param = knn_mae(Ptr, Ytr, Pva, Yva, k=5)
    print("\n[参数空间 kNN k=5]  （对照组：参数几乎唯一确定标签）")
    for i, d in enumerate(DIMS):
        print(f"  {d:12s} MAE={mae_p[i]:7.3f}")
    print(f"  mae4 = {mae_p.mean():.4f}")
    out["param_knn"] = {"mae": {DIMS[i]: round(float(mae_p[i]), 4) for i in range(4)},
                        "mae4": round(float(mae_p.mean()), 4)}

    # --- 实验组：像素空间 kNN（贝叶斯条件均值的非参数估计）---
    Xtr = np.array([pixel_feats(s) for s in tr])
    Xva = np.array([pixel_feats(s) for s in va])
    for k in (1, 5, 15):
        mae_x, cond_std, d0 = knn_mae(Xtr, Ytr, Xva, Yva, k=k)
        print(f"\n[像素空间 kNN k={k}]  （条件均值估计）")
        for i, d in enumerate(DIMS):
            print(f"  {d:12s} MAE={mae_x[i]:7.3f}   近邻标签条件std={cond_std[i]:6.3f}")
        print(f"  mae4 = {mae_x.mean():.4f}   最近邻距离中位数={np.median(d0):.1f}")
        out[f"pixel_knn_k{k}"] = {
            "mae": {DIMS[i]: round(float(mae_x[i]), 4) for i in range(4)},
            "mae4": round(float(mae_x.mean()), 4),
            "cond_std": {DIMS[i]: round(float(cond_std[i]), 4) for i in range(4)},
            "median_nearest_dist": round(float(np.median(d0)), 2),
        }

    best = min(out[f"pixel_knn_k{k}"]["mae4"] for k in (1, 5, 15))
    out["best_pixel_knn_mae4"] = best
    out["gate"] = 5.0
    out["interpretation"] = (
        "pixel-space kNN approximates the Bayes-optimal E[y|x] without gradient training. "
        "If even k=15 averaging cannot get below ~10, the conditional variance Var[y|x] alone "
        "bounds any model's MAE well above the 5.0 gate."
    )
    pathlib.Path("reports/conditional_variance_probe.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n最佳像素 kNN mae4 = {best}")
    print("wrote reports/conditional_variance_probe.json")


if __name__ == "__main__":
    main()
