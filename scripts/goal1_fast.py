"""快速重训（goal①）：把全部图像预加载进内存张量，消除每步 PNG 解码瓶颈。
原 goal1_train.py 每步读 32 张 PNG → 单步 ~3.3s，14000 步需 13 小时。
预加载后单步只做 forward/backward，可提速 10x 以上。

内存预算：2000 张 × 3×224×224×4B ≈ 1.2 GB（float32）。用 uint8 存（~300MB），
取 batch 时再归一化。
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
OUT = pathlib.Path("checkpoints/goal1")
CKPT = OUT / "train_latest.pt"
BEST = OUT / "best.pt"
CURVE = pathlib.Path("reports/goal1_curve.json")


def load_all(split: str, samples: list[dict]) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """返回 (uint8 NCHW, subs Nx4 float32, total Nx1 float32)。"""
    ids = [s for s in samples if split_of(s["id"]) == split]
    imgs = torch.empty((len(ids), 3, 224, 224), dtype=torch.uint8)
    subs = torch.empty((len(ids), 4), dtype=torch.float32)
    tots = torch.empty((len(ids), 1), dtype=torch.float32)
    for i, s in enumerate(ids):
        img = Image.open(os.path.join(".", s["image_path"])).convert("RGB").resize((224, 224), Image.BILINEAR)
        arr = np.asarray(img, dtype=np.uint8)
        imgs[i] = torch.from_numpy(np.ascontiguousarray(arr.transpose(2, 0, 1)))
        subs[i] = torch.tensor([float(s["labels"][k]) for k in BRANCH_KEYS])
        tots[i, 0] = float(s["labels"]["total"])
    return imgs, subs, tots


def norm(batch_u8: torch.Tensor) -> torch.Tensor:
    x = batch_u8.float().div_(255.0)
    return (x - MEAN) / STD


@torch.no_grad()
def evaluate(model, imgs, subs, tots, bs=128) -> dict:
    was = model.training
    model.eval()
    pt, ps = [], []
    for s in range(0, len(imgs), bs):
        x = norm(imgs[s:s + bs])
        out = model(x, return_ranking=False)
        pt.append(out["total"].view(-1))
        ps.append(torch.cat([out[k] for k in BRANCH_KEYS], dim=-1))
    if was:
        model.train()
    pt_t = torch.cat(pt)
    Ps = torch.cat(ps)
    mae_dims = (Ps - subs).abs().mean(dim=0)
    p, g = pt_t.tolist(), tots.view(-1).tolist()
    hits = cnt = 0.0
    n = len(p)
    for i in range(n):
        for j in range(i + 1, n):
            dy = g[i] - g[j]
            if dy == 0:
                continue
            cnt += 1
            d = p[i] - p[j]
            hits += 0.5 if d == 0 else (1.0 if d * dy > 0 else 0.0)
    a, b = np.asarray(p), np.asarray(g)
    pear = float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else float("nan")
    return {
        "n": n,
        "mae4": float(mae_dims.mean()),
        "mae_dim": {k: round(float(mae_dims[i]), 4) for i, k in enumerate(BRANCH_KEYS)},
        "pairwise": round(float(hits / cnt), 6) if cnt else float("nan"),
        "pearson": round(pear, 6),
    }


def passed(m):
    return m["mae4"] <= 5.0 and m["pairwise"] >= 0.68 and m["pearson"] >= 0.70


def main():
    steps = int(os.environ.get("STEPS", "14000"))
    bs = int(os.environ.get("BS", "32"))
    lr0 = float(os.environ.get("LR", "3e-4"))
    lr_min = float(os.environ.get("LR_MIN", "1e-5"))
    seed = int(os.environ.get("SEED", "42"))
    eval_every = int(os.environ.get("EVAL_EVERY", "250"))
    resume = os.environ.get("RESUME", "") not in ("", "0", "false")

    OUT.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    torch.set_num_threads(max(1, (os.cpu_count() or 4)))

    samples = json.loads(pathlib.Path("data/synthetic/index.json").read_text(encoding="utf-8"))["samples"]
    t_load = time.time()
    tr_i, tr_s, tr_t = load_all("train", samples)
    va_i, va_s, va_t = load_all("val", samples)
    print(f"[fast] loaded train={len(tr_i)} val={len(va_i)} in {time.time()-t_load:.0f}s "
          f"(uint8 cache {(tr_i.numel()+va_i.numel())/1e6:.0f} MB)", flush=True)

    model = teacher()
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[fast] params={n_params:,} within_budget={n_params < 10_000_000}", flush=True)
    model.train()
    opt = tcli._optimizer(model)

    start = 0
    curve = []
    best = {"mae4": float("inf")}
    order_rng = random.Random(seed)
    perm = list(range(len(tr_i)))
    order_rng.shuffle(perm)
    cursor = 0

    if resume and CKPT.exists():
        b = torch.load(CKPT, map_location="cpu", weights_only=False)
        model.load_state_dict(b["model"], strict=True)
        opt.load_state_dict(b["optimizer"])
        start = int(b["step"])
        curve = b.get("curve", [])
        best = b.get("best", best)
        perm = b["perm"]; cursor = b["cursor"]; order_rng.setstate(tuple(b["rng_state"]))
        cursor = 0  # 简化：续跑从头扫，不影响收敛
        print(f"[fast] resumed step {start} best={best}", flush=True)

    t0 = time.time()
    for step in range(start + 1, steps + 1):
        prog = step / steps
        lr = lr_min + 0.5 * (lr0 - lr_min) * (1 + math.cos(math.pi * prog))
        for g in opt.param_groups:
            g["lr"] = lr
        if cursor + bs > len(perm):
            order_rng.shuffle(perm)
            cursor = 0
        idxs = perm[cursor:cursor + bs]
        cursor += bs
        x = norm(tr_i[idxs])
        subs = tr_s[idxs]
        tots = tr_t[idxs]
        out = model(x)
        loss = tcli.regression_loss(out, tots, subs)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()

        if step % eval_every == 0 or step == steps:
            m = evaluate(model, va_i, va_s, va_t)
            rec = {"step": step, "lr": round(lr, 8), "loss": round(float(loss.detach()), 4), **m}
            curve.append(rec)
            print(f"[fast] step {step}/{steps} loss={rec['loss']:.3f} "
                  f"val mae4={m['mae4']:.4f} pair={m['pairwise']:.4f} pearson={m['pearson']:.4f} "
                  f"({time.time()-t0:.0f}s) pass={passed(m)}", flush=True)
            if m["mae4"] < best["mae4"]:
                best = dict(m, step=step)
                torch.save({"step": step, "model": model.state_dict(), "best": best,
                            "params": n_params}, BEST)
            torch.save({"step": step, "model": model.state_dict(), "optimizer": opt.state_dict(),
                        "curve": curve, "best": best, "params": n_params,
                        "perm": perm, "cursor": cursor,
                        "rng_state": order_rng.getstate()}, CKPT)
            CURVE.write_text(json.dumps({"params": n_params, "steps": steps, "bs": bs, "lr": lr0,
                                         "train_n": len(tr_i), "val_n": len(va_i),
                                         "best": best, "curve": curve}, indent=2), encoding="utf-8")
            if passed(m):
                print(f"[fast] GATE PASSED at step {step}", flush=True)
                break

    report = {"params": n_params, "budget": 10_000_000, "steps": steps, "bs": bs, "lr": lr0,
              "train_n": len(tr_i), "val_n": len(va_i), "best": best,
              "elapsed_s": round(time.time() - t0, 1), "curve": curve}
    pathlib.Path("reports/goal1_train.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[fast] done best={json.dumps(best, ensure_ascii=False)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
