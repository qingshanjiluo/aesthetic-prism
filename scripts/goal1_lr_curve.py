"""round5 关键实验：训练量 vs 泛化能力的曲线。

问题：过拟合测试证明 32 张图能到 train_mae4=0.009。正式训练 1603 张 500 步只有 train 11.07 / val 12.09。
到底是「步数不够」还是「信息不可泛化」？

方法：固定超参（lr=1e-3, bs=64），从 0 开始训练，每 200 步记录 train 与 val 的 mae4，跑 2000 步。
  - 若 train 持续下降而 val 停在 ~11  → 过拟合 / 信息不可泛化
  - 若 train 与 val 同步下降但都慢    → 纯训练量问题
  - 若两者都在 2000 步内接近 5.0     → 门限可达

为控制时间，train 只采样 400 张（每 200 步 = 约 32 epoch），val 用全量 208。
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
from PIL import Image

from aesthetic_prism.data.schema import split_of
from aesthetic_prism.model.model import BRANCH_KEYS, teacher
from aesthetic_prism.train import cli as tcli

MEAN = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32).view(1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32).view(1, 3, 1, 1)
DIMS = BRANCH_KEYS
N_TRAIN = int(os.environ.get("N_TRAIN", "400"))


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
    return float(d.mean()), {DIMS[i]: round(float(d[i]), 2) for i in range(4)}, P


def main():
    steps = int(os.environ.get("STEPS", "2000"))
    bs = int(os.environ.get("BS", "64"))
    lr = float(os.environ.get("LR", "1e-3"))
    eval_every = int(os.environ.get("EVAL_EVERY", "200"))
    seed = 42
    torch.manual_seed(seed); np.random.seed(seed); random.seed(seed)
    torch.set_num_threads(max(1, os.cpu_count() or 4))

    samples = json.loads(pathlib.Path("data/synthetic/index.json").read_text(encoding="utf-8"))["samples"]
    tr_i, tr_s, tr_t = load("train", samples, limit=N_TRAIN)
    va_i, va_s, _ = load("val", samples)
    print(f"[lr-curve] train={len(tr_i)} val={len(va_i)} steps={steps} bs={bs} lr={lr}", flush=True)

    model = teacher()
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
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
        out = model(norm(tr_i[idx]))
        loss = tcli.regression_loss(out, tr_t[idx], tr_s[idx])
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        opt.step()

        if step % eval_every == 0 or step == steps:
            tr_mae, tr_dims, _ = mae4_of(model, tr_i, tr_s)
            va_mae, va_dims, _ = mae4_of(model, va_i, va_s)
            rec = {"step": step, "loss": round(float(loss.detach()), 3),
                   "train_mae4": round(tr_mae, 3), "val_mae4": round(va_mae, 3),
                   "gap": round(va_mae - tr_mae, 3),
                   "train_dims": tr_dims, "val_dims": va_dims,
                   "epochs": round(step * bs / len(tr_i), 1)}
            curve.append(rec)
            print(f"[lr-curve] step {step} ep={rec['epochs']:.0f} loss={rec['loss']:.1f} "
                  f"TRAIN={tr_mae:.2f} VAL={va_mae:.2f} gap={rec['gap']:+.2f} "
                  f"({time.time()-t0:.0f}s)", flush=True)
            pathlib.Path("reports/train_val_curve.json").write_text(
                json.dumps({"n_train": len(tr_i), "bs": bs, "lr": lr, "curve": curve}, indent=2),
                encoding="utf-8")
            if va_mae <= 5.0:
                print(f"[lr-curve] VAL mae4 reached 5.0 at step {step}", flush=True)
                break

    print(f"[lr-curve] done. final: {curve[-1] if curve else 'none'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
