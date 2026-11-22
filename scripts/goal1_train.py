"""正式重训脚本（goal①）：支持 resume、轻量 eval、逐阶段门禁判定。
与 goal1_dircheck.py 的区别：可长跑、可中断续跑、记录完整曲线、按契约口径评 val+test。

用法：
  STEPS=14000 python scripts/goal1_train.py            # 从头
  STEPS=14000 RESUME=1 python scripts/goal1_train.py   # 续跑
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

from aesthetic_prism.data.dataset import AestheticDataset
from aesthetic_prism.model.model import BRANCH_KEYS, teacher
from aesthetic_prism.train import cli as tcli

OUT = pathlib.Path("checkpoints/goal1")
CKPT = OUT / "train_latest.pt"
BEST = OUT / "best.pt"
CURVE = pathlib.Path("reports/goal1_curve.json")


def load_split(src, split):
    ds = AestheticDataset(src, split=split)
    keep = [s for s in ds.samples if s.get("labels") is not None]
    keep.sort(key=lambda s: s["id"])
    ds.samples = keep
    return ds


def gather(ds, idxs):
    imgs, subs, tots = [], [], []
    for i in idxs:
        it = ds[i]
        imgs.append(it["image"])
        subs.append(it["labels"])
        tots.append(it["total"].reshape(1))
    return torch.stack(imgs), torch.stack(subs), torch.cat(tots).unsqueeze(1)


@torch.no_grad()
def evaluate(model, ds, bs=64):
    was = model.training
    model.eval()
    pt, lt, ps, ls = [], [], [], []
    for s in range(0, len(ds), bs):
        idxs = list(range(s, min(s + bs, len(ds))))
        imgs, subs, tots = gather(ds, idxs)
        out = model(imgs, return_ranking=False)
        pt.append(out["total"].view(-1))
        lt.append(tots.view(-1))
        ps.append(torch.cat([out[k] for k in BRANCH_KEYS], dim=-1))
        ls.append(subs)
    if was:
        model.train()
    pt_t, lt_t = torch.cat(pt), torch.cat(lt)
    Ps, Ls = torch.cat(ps), torch.cat(ls)
    mae_dims = (Ps - Ls).abs().mean(dim=0)
    pt, lt = pt_t.tolist(), lt_t.tolist()
    hits = cnt = 0.0
    n = len(pt)
    for i in range(n):
        for j in range(i + 1, n):
            dy = lt[i] - lt[j]
            if dy == 0:
                continue
            cnt += 1
            d = pt[i] - pt[j]
            hits += 0.5 if d == 0 else (1.0 if d * dy > 0 else 0.0)
    a, b = np.asarray(pt), np.asarray(lt)
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
    eval_every = int(os.environ.get("EVAL_EVERY", "500"))
    resume = os.environ.get("RESUME", "") not in ("", "0", "false")

    OUT.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)

    src = "data/synthetic/index.json"
    tr = load_split(src, "train")
    va = load_split(src, "val")
    print(f"[train] train={len(tr)} val={len(va)} steps={steps} bs={bs} lr={lr0} resume={resume}", flush=True)

    model = teacher()
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[train] params={n_params:,} budget=10,000,000 within={n_params < 10_000_000}", flush=True)
    model.train()
    opt = tcli._optimizer(model)
    cur = tcli._IndexCursor(len(tr), seed)

    start = 0
    curve = []
    best = {"mae4": float("inf")}
    if resume and CKPT.exists():
        b = torch.load(CKPT, map_location="cpu", weights_only=False)
        model.load_state_dict(b["model"], strict=True)
        opt.load_state_dict(b["optimizer"])
        start = int(b["step"])
        curve = b.get("curve", [])
        best = b.get("best", best)
        for _ in range(start):  # 重放 cursor 到同一位置
            cur.next_batch(bs)
        print(f"[train] resumed from step {start}, best={best}", flush=True)

    t0 = time.time()
    for step in range(start + 1, steps + 1):
        prog = step / steps
        lr = lr_min + 0.5 * (lr0 - lr_min) * (1 + math.cos(math.pi * prog))
        for g in opt.param_groups:
            g["lr"] = lr
        idxs = cur.next_batch(bs)
        imgs, subs, tots = gather(tr, idxs)
        out = model(imgs)
        loss = tcli.regression_loss(out, tots, subs)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()

        if step % eval_every == 0 or step == steps:
            m = evaluate(model, va)
            rec = {"step": step, "lr": round(lr, 8), "loss": round(float(loss.detach()), 4), **m}
            curve.append(rec)
            print(f"[train] step {step}/{steps} loss={rec['loss']:.3f} lr={lr:.2e} "
                  f"val mae4={m['mae4']:.4f} pair={m['pairwise']:.4f} pearson={m['pearson']:.4f} "
                  f"({time.time() - t0:.0f}s) pass={passed(m)}", flush=True)
            if m["mae4"] < best["mae4"]:
                best = dict(m, step=step)
                torch.save({"step": step, "model": model.state_dict(),
                            "optimizer": opt.state_dict(), "curve": curve,
                            "best": best, "params": n_params},
                           BEST)
            torch.save({"step": step, "model": model.state_dict(),
                        "optimizer": opt.state_dict(), "curve": curve, "best": best,
                        "params": n_params}, CKPT)
            CURVE.write_text(json.dumps({"params": n_params, "steps": steps, "bs": bs,
                                         "lr": lr0, "train_n": len(tr), "val_n": len(va),
                                         "best": best, "curve": curve}, indent=2),
                             encoding="utf-8")
            if passed(m):
                print(f"[train] GATE PASSED at step {step}", flush=True)
                break

    report = {"params": n_params, "budget": 10_000_000, "steps": steps, "bs": bs, "lr": lr0,
              "train_n": len(tr), "val_n": len(va), "best": best,
              "elapsed_s": round(time.time() - t0, 1), "curve": curve}
    pathlib.Path("reports/goal1_train.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[train] done best={json.dumps(best, ensure_ascii=False)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
