"""GAP 假设判决实验：Branch 的全局平均池化是否抹掉了 composition 需要的空间信息。

假设：composition 主导参数 d3（主体从中心向三分点移动的比例）与 w（左右视觉权重）
都是纯空间量，而 Branch 在 proj 之前做 AdaptiveAvgPool2d(1)=GAP，把 (N,C,14,14)
压成 (N,C,1,1)，空间索引全部消失 → d3/w 在 GAP 后不可恢复。

判决方法：只改 Branch 的池化方式（GAP → 3x3 或 4x4 网格池化），其余不动，
同一个训练脚本跑同样步数，比较 composition 维的 mae 与 std_ratio。
若网格池化让 composition 明显改善且 light 不变差，则假设成立。

本实验用「只训练单个 Branch + score_head 的一个分支」的轻量代理：
直接取 trunk 输出特征（用随机初始化 trunk，因为要测的是池化方式对可学习性的影响），
在固定特征上比较两种池化下的线性/非线性映射能力。更快且结论清晰。
"""
from __future__ import annotations

import json
import os
import pathlib
import random
import sys
import time

AP_ROOT = os.environ.get("AP_ROOT") or os.getcwd()
sys.path.insert(0, os.path.join(AP_ROOT, "src"))
os.chdir(AP_ROOT)

import numpy as np
import torch
import torch.nn as nn
from PIL import Image

from aesthetic_prism.data.schema import split_of

MEAN = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32).view(1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32).view(1, 3, 1, 1)
DIMS = ("composition", "light", "creativity", "story")


def load(split, samples, n_limit=None):
    ids = [s for s in samples if split_of(s["id"]) == split]
    if n_limit:
        ids = ids[:n_limit]
    imgs = torch.empty((len(ids), 3, 224, 224), dtype=torch.uint8)
    labs = torch.empty((len(ids), 4), dtype=torch.float32)
    for i, s in enumerate(ids):
        img = Image.open(os.path.join(".", s["image_path"])).convert("RGB").resize((224, 224), Image.BILINEAR)
        imgs[i] = torch.from_numpy(np.ascontiguousarray(np.asarray(img, dtype=np.uint8).transpose(2, 0, 1)))
        labs[i] = torch.tensor([float(s["labels"][k]) for k in DIMS])
    return imgs, labs


def norm(b):
    return (b.float().div_(255.0) - MEAN) / STD


class Head(nn.Module):
    """特征提取器（固定）+ 可训练头。pool_mode: 'gap' 或 'grid3'/'grid4'。"""

    def __init__(self, feat_dim=128, pool_mode="gap", out_dim=1):
        super().__init__()
        self.pool_mode = pool_mode
        if pool_mode == "gap":
            self.pool = nn.AdaptiveAvgPool2d(1)
            in_dim = feat_dim
        else:
            g = int(pool_mode[-1])
            self.pool = nn.AdaptiveAvgPool2d(g)
            in_dim = feat_dim * g * g
        self.fc = nn.Sequential(nn.Linear(in_dim, 128), nn.GELU(), nn.Linear(128, out_dim))

    def forward(self, feat):
        x = self.pool(feat).flatten(1)
        return self.fc(x)


def main():
    torch.manual_seed(0)
    np.random.seed(0)
    random.seed(0)
    torch.set_num_threads(4)

    samples = json.loads(pathlib.Path("data/synthetic/index.json").read_text(encoding="utf-8"))["samples"]
    tr_i, tr_l = load("train", samples, n_limit=400)
    va_i, va_l = load("val", samples, n_limit=100)
    print(f"[gap-exp] train={len(tr_i)} val={len(va_i)}", flush=True)

    # 固定特征提取器：用 teacher 的 stem+trunk（不训练，只为得到 (N,128,14,14)）
    from aesthetic_prism.model.model import teacher
    t = teacher()
    t.eval()
    for p in t.parameters():
        p.requires_grad_(False)

    with torch.no_grad():
        def feats(imgs, bs=16):
            out = []
            for i in range(0, len(imgs), bs):
                x = norm(imgs[i:i + bs])
                out.append(t.trunk(t.stem(x)))
            return torch.cat(out)
        Ftr = feats(tr_i)
        Fva = feats(va_i)
    print(f"[gap-exp] feature shape: {tuple(Ftr.shape)}", flush=True)

    results = {}
    for mode in ("gap", "grid3", "grid4"):
        per_dim = {}
        for di, dim in enumerate(DIMS):
            h = Head(feat_dim=Ftr.shape[1], pool_mode=mode, out_dim=1)
            opt = torch.optim.Adam(h.parameters(), lr=3e-3)
            ytr = tr_l[:, di:di + 1]
            yva = va_l[:, di:di + 1]
            bs = 64
            for ep in range(30):
                perm = torch.randperm(len(Ftr))
                for k in range(0, len(Ftr), bs):
                    idx = perm[k:k + bs]
                    pred = h(Ftr[idx])
                    loss = (pred - ytr[idx]).pow(2).mean()
                    opt.zero_grad(set_to_none=True)
                    loss.backward()
                    opt.step()
            with torch.no_grad():
                pv = h(Fva)
                mae = float((pv - yva).abs().mean())
                ratio = float(pv.std() / max(float(yva.std()), 1e-9))
            per_dim[dim] = {"mae": round(mae, 4), "std_ratio": round(ratio, 3)}
        results[mode] = per_dim
        maes = [per_dim[d]["mae"] for d in DIMS]
        print(f"[gap-exp] {mode:6s} mae4={np.mean(maes):.4f}  " +
              "  ".join(f"{d[:4]}={per_dim[d]['mae']:.3f}(r={per_dim[d]['std_ratio']:.2f})" for d in DIMS), flush=True)

    out = {"experiment": "pooling mode vs per-dim learnability (frozen teacher trunk features)",
           "n_train": len(Ftr), "n_val": len(Fva), "results": results}
    pathlib.Path("reports/gap_pooling_experiment.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nwrote reports/gap_pooling_experiment.json")


if __name__ == "__main__":
    main()
