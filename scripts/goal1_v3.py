"""根因验证 + 修复实验：sigmoid 输出头的动态范围压制问题。

诊断（上一轮实测，artifacts/student.onnx 在 val 前 60 张）：
  composition pred_std/gt_std = 0.343, creativity = 0.296, light = 0.725, story = 0.703
即预测动态范围只有标签的 30%~70%，模型塌缩在均值附近 → mae4 无法下降。

机制：ScoreHead 输出 100*sigmoid(z)。当 s≈0.5 时 d(out)/dz = 100*0.25 = 25，
而标签 std≈18 → 需要 z_std≈0.72。但平方误差对 z 的梯度被 0.25 因子额外压 4 倍，
且 sigmoid 在两端饱和，模型容易停在"输出均值"这个低能量局部解。

修复（不改模型结构、不改契约）：
  训练期对每个维度做标签标准化 z = (y - mean) / std，
  再对预测值用同一变换后算 MSE；推理时输出仍经 sigmoid*100，
  但标准化后的目标把梯度尺度拉回 O(1)，sigmoid 不再被压制。
  等价实现：损失里给每维乘 1/std² 权重（这就是标准化 MSE 的展开形式）。

本脚本对比三种损失：
  L0 = 原 regression_loss（total SE + 0.25*Σ sub SE）
  L1 = 每维标准化 MSE（除以该维标签方差）
  L2 = L1 + 显式方差匹配项（惩罚 pred_std 远小于 gt_std）
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
OUT = pathlib.Path("checkpoints/goal1v3")


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


def norm(b):
    return (b.float().div_(255.0) - MEAN) / STD


def augment(batch_u8, gen):
    n = batch_u8.shape[0]
    x = batch_u8.float()
    m = torch.rand(n, generator=gen) < 0.5
    if m.any():
        x[m] = torch.flip(x[m], dims=[-1])
    b = (torch.rand(n, 1, 1, 1, generator=gen) * 2 - 1) * 20.0
    c = 1.0 + (torch.rand(n, 1, 1, 1, generator=gen) * 2 - 1) * 0.16
    return (x * c + b).clamp_(0, 255).to(torch.uint8)


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
    pt_t, Ps = torch.cat(pt), torch.cat(ps)
    mae_dims = (Ps - subs).abs().mean(dim=0)
    g_vec = tots.view(-1)
    dy = g_vec.unsqueeze(0) - g_vec.unsqueeze(1)
    ds = pt_t.unsqueeze(0) - pt_t.unsqueeze(1)
    upper = torch.triu(torch.ones_like(dy, dtype=torch.bool), diagonal=1)
    valid = upper & (dy != 0)
    cnt = float(valid.sum())
    if cnt:
        sg = torch.sign(ds[valid]) * torch.sign(dy[valid])
        pw = (float((sg > 0).sum()) + 0.5 * float((sg == 0).sum())) / cnt
    else:
        pw = float("nan")
    a, b = pt_t.numpy(), g_vec.numpy()
    pear = float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else float("nan")
    return {
        "n": len(a), "mae4": float(mae_dims.mean()),
        "mae_dim": {k: round(float(mae_dims[i]), 4) for i, k in enumerate(BRANCH_KEYS)},
        "pairwise": round(pw, 6), "pearson": round(pear, 6),
        "std_ratio": {k: round(float(Ps[:, i].std() / max(subs[:, i].std(), 1e-9)), 3)
                      for i, k in enumerate(BRANCH_KEYS)},
        "total_std_ratio": round(float(pt_t.std() / max(g_vec.std(), 1e-9)), 3),
    }


def loss_standardized(out, tots, subs, sub_std, tot_std):
    """每维标准化 MSE：把梯度尺度拉回 O(1)，解除 sigmoid 动态范围压制。"""
    pred_sub = torch.cat([out[k] for k in BRANCH_KEYS], dim=-1)
    per_dim = ((pred_sub - subs) / sub_std).pow(2).mean(dim=0)     # (4,) 每维标准化 MSE
    total_term = ((out["total"].reshape(-1) - tots.reshape(-1)) / tot_std).pow(2).mean()
    return total_term + per_dim.mean()


def main():
    steps = int(os.environ.get("STEPS", "3000"))
    bs = int(os.environ.get("BS", "32"))
    lr0 = float(os.environ.get("LR", "4e-4"))
    lr_min = float(os.environ.get("LR_MIN", "1e-5"))
    seed = int(os.environ.get("SEED", "42"))
    eval_every = int(os.environ.get("EVAL_EVERY", "250"))

    OUT.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(seed); np.random.seed(seed); random.seed(seed)
    torch.set_num_threads(max(1, os.cpu_count() or 4))
    gen = torch.Generator().manual_seed(seed + 1)

    samples = json.loads(pathlib.Path("data/synthetic/index.json").read_text(encoding="utf-8"))["samples"]
    tr_i, tr_s, tr_t = load_all("train", samples)
    va_i, va_s, va_t = load_all("val", samples)
    # 用 train 统计量做标准化（不偷看 val/test）
    sub_std = tr_s.std(dim=0).clamp_min(1e-6)
    tot_std = tr_t.std().clamp_min(1e-6)
    print(f"[v3] train={len(tr_i)} val={len(va_i)} steps={steps}")
    print(f"[v3] train sub_std={sub_std.tolist()} tot_std={float(tot_std):.3f}")

    model = teacher()
    model.train()
    opt = tcli._optimizer(model)
    curve, best = [], {"mae4": float("inf")}
    perm = list(range(len(tr_i)))
    random.Random(seed).shuffle(perm)
    cur = 0
    t0 = time.time()

    for step in range(1, steps + 1):
        prog = step / steps
        lr = lr_min + 0.5 * (lr0 - lr_min) * (1 + math.cos(math.pi * prog))
        for g in opt.param_groups:
            g["lr"] = lr
        if cur + bs > len(perm):
            random.Random(seed + step).shuffle(perm)
            cur = 0
        idxs = perm[cur:cur + bs]
        cur += bs
        x = norm(augment(tr_i[idxs], gen))
        subs, tots = tr_s[idxs], tr_t[idxs]
        out = model(x)
        loss = loss_standardized(out, tots, subs, sub_std, tot_std)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        opt.step()

        if step % eval_every == 0 or step == steps:
            m = evaluate(model, va_i, va_s, va_t)
            rec = {"step": step, "loss": round(float(loss.detach()), 4), **m}
            curve.append(rec)
            print(f"[v3] step {step} loss={rec['loss']:.3f} mae4={m['mae4']:.4f} "
                  f"pair={m['pairwise']:.4f} pearson={m['pearson']:.4f} "
                  f"std_ratio={m['std_ratio']} tot_ratio={m['total_std_ratio']} ({time.time()-t0:.0f}s)")
            if m["mae4"] < best["mae4"]:
                best = dict(m, step=step)
                torch.save({"step": step, "model": model.state_dict(), "best": best},
                           OUT / "best.pt")
            pathlib.Path("reports/goal1v3_curve.json").write_text(
                json.dumps({"best": best, "curve": curve}, indent=2), encoding="utf-8")
            if m["mae4"] <= 5.0 and m["pairwise"] >= 0.68 and m["pearson"] >= 0.70:
                print(f"[v3] GATE PASSED at step {step}")
                break

    print(f"[v3] done best_mae4={best['mae4']:.4f} std_ratio={best.get('std_ratio')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
