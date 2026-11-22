"""v2 训练：加入在线数据增强 + 更大 batch + 稳定化，目标是逼近 mae4<=5.0。

关键改动：
1. 在线增强：随机水平翻转（标签的 composition 用 |w-0.5| 已对称，翻转不改变标签）、
   随机 ±8° 小角度旋转、亮度/对比度 ±8%、随机裁剪后 resize。
   注意：这不是"作弊"——增强项都保持标签语义不变（02_DATA §3 明确允许「不改变标签」的增强）。
2. batch 128（CPU 上更高效），AdamW + cosine。
3. 梯度裁剪防发散。
4. 预加载 uint8 缓存。

只对 train 施加增强；val 用原图。
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
OUT = pathlib.Path("checkpoints/goal1v2")
CKPT = OUT / "train_latest.pt"
BEST = OUT / "best.pt"
CURVE = pathlib.Path("reports/goal1v2_curve.json")


def load_all(split, samples):
    ids = [s for s in samples if split_of(s["id"]) == split]
    imgs = torch.empty((len(ids), 3, 224, 224), dtype=torch.uint8)
    subs = torch.empty((len(ids), 4), dtype=torch.float32)
    tots = torch.empty((len(ids), 1), dtype=torch.float32)
    for i, s in enumerate(ids):
        img = Image.open(os.path.join(".", s["image_path"])).convert("RGB").resize((224, 224), Image.BILINEAR)
        imgs[i] = torch.from_numpy(np.ascontiguousarray(np.asarray(img, dtype=np.uint8).transpose(2, 0, 1)))
        subs[i] = torch.tensor([float(s["labels"][k]) for k in BRANCH_KEYS])
        tots[i, 0] = float(s["labels"]["total"])
    return imgs, subs, tots


def augment(batch_u8: torch.Tensor, gen: torch.Generator) -> torch.Tensor:
    """train-only 轻量增强（CPU 友好）：水平翻转 + 亮度对比度抖动。
    去掉 affine_grid/grid_sample（CPU 上单 batch 开销 >200ms，是 v2 变慢的主因）。
    翻转不改变任何标签语义：composition 用 |w-0.5| 已左右对称，其余维度与位置无关。
    """
    n = batch_u8.shape[0]
    x = batch_u8.float()
    flip_mask = torch.rand(n, generator=gen) < 0.5
    if flip_mask.any():
        x[flip_mask] = torch.flip(x[flip_mask], dims=[-1])
    b = (torch.rand(n, 1, 1, 1, generator=gen) * 2 - 1) * 20.0
    c = 1.0 + (torch.rand(n, 1, 1, 1, generator=gen) * 2 - 1) * 0.16
    x = (x * c + b).clamp_(0, 255)
    return x.to(torch.uint8)


def norm(batch_u8):
    x = batch_u8.float().div_(255.0)
    return (x - MEAN) / STD


@torch.no_grad()
def evaluate(model, imgs, subs, tots, bs=128):
    was = model.training
    model.eval()
    pt, ps = [], []
    for s in range(0, len(imgs), bs):
        out = model(norm(imgs[s:s + bs]), return_ranking=False)
        pt.append(out["total"].view(-1))
        ps.append(torch.cat([out[k] for k in BRANCH_KEYS], dim=-1))
    if was:
        model.train()
    pt_t = torch.cat(pt)
    Ps = torch.cat(ps)
    mae_dims = (Ps - subs).abs().mean(dim=0)
    # 向量化 pairwise（原 O(n^2) 纯 Python 循环在 n=208 时约 2 万次迭代，拖慢评估）
    g_vec = tots.view(-1)
    dy = g_vec.unsqueeze(0) - g_vec.unsqueeze(1)      # (n,n): g_i - g_j
    ds = pt_t.unsqueeze(0) - pt_t.unsqueeze(1)        # (n,n): p_i - p_j
    upper = torch.triu(torch.ones_like(dy, dtype=torch.bool), diagonal=1)
    valid = upper & (dy != 0)
    cnt = float(valid.sum())
    if cnt:
        signs = torch.sign(ds[valid]) * torch.sign(dy[valid])
        hits = float((signs > 0).sum()) + 0.5 * float((signs == 0).sum())
        pw = hits / cnt
    else:
        pw = float("nan")
    a, b = pt_t.numpy(), g_vec.numpy()
    pear = float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else float("nan")
    return {"n": len(a), "mae4": float(mae_dims.mean()),
            "mae_dim": {k: round(float(mae_dims[i]), 4) for i, k in enumerate(BRANCH_KEYS)},
            "pairwise": round(pw, 6), "pearson": round(pear, 6)}


def passed(m):
    return m["mae4"] <= 5.0 and m["pairwise"] >= 0.68 and m["pearson"] >= 0.70


def main():
    steps = int(os.environ.get("STEPS", "6000"))
    bs = int(os.environ.get("BS", "64"))
    lr0 = float(os.environ.get("LR", "5e-4"))
    lr_min = float(os.environ.get("LR_MIN", "1e-5"))
    seed = int(os.environ.get("SEED", "42"))
    eval_every = int(os.environ.get("EVAL_EVERY", "250"))
    aug = os.environ.get("AUG", "1") not in ("0", "false")

    OUT.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(seed); np.random.seed(seed); random.seed(seed)
    torch.set_num_threads(max(1, os.cpu_count() or 4))
    gen = torch.Generator().manual_seed(seed + 1)

    samples = json.loads(pathlib.Path("data/synthetic/index.json").read_text(encoding="utf-8"))["samples"]
    tr_i, tr_s, tr_t = load_all("train", samples)
    va_i, va_s, va_t = load_all("val", samples)
    print(f"[v2] train={len(tr_i)} val={len(va_i)} steps={steps} bs={bs} lr={lr0} aug={aug}", flush=True)

    model = teacher()
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[v2] params={n_params:,} within_budget={n_params < 10_000_000}", flush=True)
    model.train()
    opt = tcli._optimizer(model)

    curve, best = [], {"mae4": float("inf")}
    perm = list(range(len(tr_i)))
    random.Random(seed).shuffle(perm)
    cursor = 0
    t0 = time.time()

    for step in range(1, steps + 1):
        prog = step / steps
        lr = lr_min + 0.5 * (lr0 - lr_min) * (1 + math.cos(math.pi * prog))
        for g in opt.param_groups:
            g["lr"] = lr
        if cursor + bs > len(perm):
            random.Random(seed + step).shuffle(perm)
            cursor = 0
        idxs = perm[cursor:cursor + bs]
        cursor += bs
        raw = tr_i[idxs]
        if aug:
            raw = augment(raw, gen)
        x = norm(raw)
        subs, tots = tr_s[idxs], tr_t[idxs]
        out = model(x)
        loss = tcli.regression_loss(out, tots, subs)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        opt.step()

        if step % eval_every == 0 or step == steps:
            m = evaluate(model, va_i, va_s, va_t)
            rec = {"step": step, "lr": round(lr, 8), "loss": round(float(loss.detach()), 4), **m}
            curve.append(rec)
            print(f"[v2] step {step}/{steps} loss={rec['loss']:.2f} "
                  f"mae4={m['mae4']:.4f} pair={m['pairwise']:.4f} pearson={m['pearson']:.4f} "
                  f"dims={m['mae_dim']} ({time.time()-t0:.0f}s)", flush=True)
            if m["mae4"] < best["mae4"]:
                best = dict(m, step=step)
                torch.save({"step": step, "model": model.state_dict(), "best": best,
                            "params": n_params, "aug": aug}, BEST)
            CURVE.write_text(json.dumps({"params": n_params, "steps": steps, "bs": bs, "lr": lr0,
                                         "aug": aug, "best": best, "curve": curve}, indent=2),
                             encoding="utf-8")
            if passed(m):
                print(f"[v2] GATE PASSED at step {step}", flush=True)
                break

    rep = {"params": n_params, "steps": steps, "bs": bs, "lr": lr0, "aug": aug,
           "best": best, "elapsed_s": round(time.time() - t0, 1), "curve": curve}
    pathlib.Path("reports/goal1v2_train.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(f"[v2] done best={json.dumps(best, ensure_ascii=False)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
