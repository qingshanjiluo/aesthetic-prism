"""方向验证：N=2000 时小步数训练能否把契约口径 val mae4 压下来。
目的不是产出交付模型，而是判定「扩数据是否有效」，避免盲目长跑。
用 teacher 宽度（376k，远低于 10M 预算，不剪枝），直接回归 + KD。
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
def evaluate(model, ds, bs=32):
    was = model.training
    model.eval()
    pt, lt, ps, ls = [], [], [], []
    for s in range(0, len(ds), bs):
        idxs = list(range(s, min(s + bs, len(ds))))
        imgs, subs, tots = gather(ds, idxs)
        out = model(imgs, return_ranking=False)
        pt.append(out["total"].view(-1)); lt.append(tots.view(-1))
        ps.append(torch.cat([out[k] for k in BRANCH_KEYS], dim=-1)); ls.append(subs)
    if was:
        model.train()
    pt, lt = torch.cat(pt).tolist(), torch.cat(lt).tolist()
    Ps, Ls = torch.cat(ps), torch.cat(ls)
    mae_dims = (Ps - Ls).abs().mean(dim=0)
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
    return {"n": n, "mae4": float(mae_dims.mean()),
            "mae_dim": {k: float(mae_dims[i]) for i, k in enumerate(BRANCH_KEYS)},
            "pairwise": float(hits / cnt) if cnt else float("nan"), "pearson": pear}


def main():
    steps = int(os.environ.get("STEPS", "800"))
    bs = int(os.environ.get("BS", "32"))
    lr0 = float(os.environ.get("LR", "3e-4"))
    seed = 42
    torch.manual_seed(seed); np.random.seed(seed); random.seed(seed)

    src = "data/synthetic/index.json"
    tr = load_split(src, "train")
    va = load_split(src, "val")
    print(f"[dv] train={len(tr)} val={len(va)} steps={steps} bs={bs} lr={lr0}", flush=True)

    model = teacher()
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[dv] params={n_params:,} (budget 10,000,000)", flush=True)
    model.train()
    opt = tcli._optimizer(model)
    cur = tcli._IndexCursor(len(tr), seed)

    t0 = time.time()
    hist = []
    for step in range(1, steps + 1):
        prog = step / steps
        lr = 3e-5 + 0.5 * (lr0 - 3e-5) * (1 + math.cos(math.pi * prog))
        for g in opt.param_groups:
            g["lr"] = lr
        idxs = cur.next_batch(bs)
        imgs, subs, tots = gather(tr, idxs)
        out = model(imgs)
        loss = tcli.regression_loss(out, tots, subs)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        if step % 100 == 0 or step == steps:
            m = evaluate(model, va)
            hist.append({"step": step, **m})
            print(f"[dv] step {step} loss={float(loss.detach()):.3f} val mae4={m['mae4']:.4f} "
                  f"pair={m['pairwise']:.4f} pearson={m['pearson']:.4f} ({time.time()-t0:.0f}s)", flush=True)

    out = {"steps": steps, "bs": bs, "lr": lr0, "params": n_params,
           "train_n": len(tr), "val_n": len(va), "history": hist,
           "elapsed_s": round(time.time() - t0, 1)}
    pathlib.Path("reports/goal1_dircheck.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(hist[-1], indent=2))


if __name__ == "__main__":
    main()
