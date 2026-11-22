"""round5 核心实验结论：mae4 的真实瓶颈是泛化，不是可学性。

实验 scripts/goal1_lr_curve.py（400 train / 208 val, lr=1e-3, bs=64, N=2000 数据集）：

| step | epoch | TRAIN mae4 | VAL mae4 | gap |
|---|---|---|---|---|
| 200 | 32 | **5.251** | **12.895** | **+7.644** |

关键事实：
1. **TRAIN 达到 5.25** —— 门槛 5.0 几乎可达，说明信息存在且可学
2. **VAL 卡在 12.90** —— 泛化失败
3. gap = 7.64，且 32 epoch 就出现，说明训练样本远不足以约束 376,594 个参数

对照：
- 32 张过拟合测试：train mae4 0.009（更极端的过拟合）
- 400 张 32 epoch：train 5.25 / val 12.90
- 1603 张 500 步（约10 epoch）：train 11.07 / val 12.09（训练不足，尚未充分过拟合）

三条曲线共同指向：**val 的能力上界被数据量/多样性锁死，而不是被模型或标签锁死。**

因此修复方向是「提升泛化」，具体是：
A. 更强数据增强（几何 + 光度，且保持标签不变）
B. 正则化（dropout / weight decay / label smoothing）
C. 更小模型（减少 376k → 更匹配 1603 样本）
D. 更多训练数据（2000 → 更大）

本脚本用于比较 A/B/C 对 gap 的影响。
"""
from __future__ import annotations

import json
import math
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
from aesthetic_prism.model.model import BRANCH_KEYS, HAPNet
from aesthetic_prism.train import cli as tcli

MEAN = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32).view(1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32).view(1, 3, 1, 1)
DIMS = BRANCH_KEYS


def load(split, samples, limit=None):
    ids = [s for s in samples if split_of(s["id"]) == split]
    if limit:
        ids = ids[:limit]
    imgs = torch.empty((len(ids), 3, 224, 224), dtype=torch.uint8)
    subs = torch.empty((len(ids), 4), dtype=torch.float32)
    tots = torch.empty((len(ids), 1), dtype=torch.float32)
    for i, s in enumerate(ids):
        img = Image.open(os.path.join(".", s["image_path"])).convert("RGB").resize((224, 224), Image.BILINEAR)
        imgs[i] = torch.from_numpy(np.ascontiguousarray(np.asarray(img, dtype=np.uint8).transpose(2, 0, 1)))
        subs[i] = torch.tensor([float(s["labels"][k]) for k in DIMS])
        tots[i, 0] = float(s["labels"]["total"])
    return imgs, subs, tots


def norm(b):
    return (b.float().div_(255.0) - MEAN) / STD


def augment_strong(batch_u8, gen):
    """保持标签不变的强增强：水平翻转 + 亮度对比度 + 饱和度 + 加性噪声 + 轻微缩放。"""
    n = batch_u8.shape[0]
    x = batch_u8.float()
    m = torch.rand(n, generator=gen) < 0.5
    if m.any():
        x[m] = torch.flip(x[m], dims=[-1])
    # 亮度/对比度
    b = (torch.rand(n, 1, 1, 1, generator=gen) * 2 - 1) * 25.0
    c = 1.0 + (torch.rand(n, 1, 1, 1, generator=gen) * 2 - 1) * 0.25
    x = x * c + b
    # 饱和度（向灰度插值）
    g = x.mean(1, keepdim=True)
    sat = 1.0 + (torch.rand(n, 1, 1, 1, generator=gen) * 2 - 1) * 0.4
    x = g + (x - g) * sat
    # 加性噪声
    noise_sd = torch.rand(n, 1, 1, 1, generator=gen) * 8.0
    x = x + torch.randn(x.shape, generator=gen) * noise_sd
    return x.clamp_(0, 255).to(torch.uint8)


@torch.no_grad()
def mae4_of(model, imgs, subs, bs=64):
    was = model.training
    model.eval()
    ps = []
    for i in range(0, len(imgs), bs):
        out = model(norm(imgs[i:i + bs]), return_ranking=False)
        ps.append(torch.cat([out[k] for k in BRANCH_KEYS], dim=-1))
    if was:
        model.train()
    P = torch.cat(ps)
    d = (P - subs).abs().mean(dim=0)
    return float(d.mean()), {DIMS[i]: round(float(d[i]), 2) for i in range(4)}


def build_model(variant: str) -> HAPNet:
    if variant == "small":
        # 376k -> 约 90k：stem=16, trunk=64, D=32
        return HAPNet(stem_channels=16, trunk_channels=64, branch_feat_dim=32,
                      gate_hidden=64, ranking_hidden=64)
    return HAPNet()


def main():
    variant = os.environ.get("VARIANT", "strong_aug")
    steps = int(os.environ.get("STEPS", "600"))
    bs = int(os.environ.get("BS", "64"))
    lr = float(os.environ.get("LR", "1e-3"))
    wd = float(os.environ.get("WD", "1e-4"))
    eval_every = int(os.environ.get("EVAL_EVERY", "200"))
    seed = 42
    torch.manual_seed(seed); np.random.seed(seed); random.seed(seed)
    torch.set_num_threads(max(1, os.cpu_count() or 4))
    gen = torch.Generator().manual_seed(seed + 7)

    samples = json.loads(pathlib.Path("data/synthetic/index.json").read_text(encoding="utf-8"))["samples"]
    tr_i, tr_s, tr_t = load("train", samples, limit=int(os.environ.get("N_TRAIN", "400")))
    va_i, va_s, _ = load("val", samples)

    model = build_model(variant)
    n_par = sum(p.numel() for p in model.parameters())
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
    print(f"[{variant}] params={n_par:,} train={len(tr_i)} val={len(va_i)} steps={steps} lr={lr} wd={wd}", flush=True)

    perm = list(range(len(tr_i)))
    random.Random(seed).shuffle(perm)
    cur = 0
    curve = []
    t0 = time.time()

    for step in range(1, steps + 1):
        if cur + bs > len(perm):
            random.Random(seed + step).shuffle(perm)
            cur = 0
        idx = perm[cur:cur + bs]
        cur += bs
        raw = tr_i[idx]
        if variant in ("strong_aug", "small", "strong_aug_small"):
            raw = augment_strong(raw, gen)
        out = model(norm(raw))
        loss = tcli.regression_loss(out, tr_t[idx], tr_s[idx])
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        opt.step()

        if step % eval_every == 0 or step == steps:
            tr_mae, _ = mae4_of(model, tr_i, tr_s)
            va_mae, va_dims = mae4_of(model, va_i, va_s)
            rec = {"step": step, "loss": round(float(loss.detach()), 2),
                   "train": round(tr_mae, 3), "val": round(va_mae, 3),
                   "gap": round(va_mae - tr_mae, 3), "val_dims": va_dims,
                   "params": n_par}
            curve.append(rec)
            print(f"[{variant}] step {step} loss={rec['loss']:.1f} TRAIN={tr_mae:.2f} "
                  f"VAL={va_mae:.2f} gap={rec['gap']:+.2f} ({time.time()-t0:.0f}s)", flush=True)
            pathlib.Path(f"reports/gen_{variant}.json").write_text(
                json.dumps({"variant": variant, "params": n_par, "curve": curve}, indent=2),
                encoding="utf-8")

    print(f"[{variant}] done {curve[-1]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
