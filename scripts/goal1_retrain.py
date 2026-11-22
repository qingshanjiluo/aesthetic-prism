"""goal① 修复验证：不剪枝的学生（教师宽度 KD 蒸馏）能否过 mae4 ≤ 5.0。
依据：S6-01 硬门禁只要求 params < 10,000,000；教师 376,594 参数 / onnx 1.40MB
已远低于该预算，ρ=0.40 的剪枝把参数量从 376k 砍到 147k，是 mae4 的唯一损失源
（教师 val 4.12 已达标，学生 val 10.09）。

本脚本：以教师 best.pt 权重初始化 → KD 蒸馏（教师软标签 MSE + 真值回归）
→ 逐 eval_interval 在 val 上评测 → 保存满足 mae4≤5.0 的最优 checkpoint。
产物写 checkpoints/goal1/（不动现有 distill 产物），验通过后才替换 artifacts/student.onnx。
"""
from __future__ import annotations

import argparse
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
from aesthetic_prism.model.model import BRANCH_KEYS, HAPNet, teacher
from aesthetic_prism.train import cli as tcli

OUT_DIR = pathlib.Path("checkpoints/goal1")
REPORT = pathlib.Path("reports/goal1_retrain.json")


def load_split(src: str, split: str):
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
def eval_split(model, ds):
    was = model.training
    model.eval()
    pt, lt, ps, ls = [], [], [], []
    for start in range(0, len(ds), 16):
        idxs = list(range(start, min(start + 16, len(ds))))
        imgs, subs, tots = gather(ds, idxs)
        out = model(imgs, return_ranking=False)
        pt.append(out["total"].view(-1))
        lt.append(tots.view(-1))
        ps.append(torch.cat([out[k] for k in BRANCH_KEYS], dim=-1))
        ls.append(subs)
    if was:
        model.train()
    pt, lt = torch.cat(pt), torch.cat(lt)
    ps, ls = torch.cat(ps), torch.cat(ls)
    mae_dims = (ps - ls).abs().mean(dim=0)
    # pairwise on total
    p = pt.tolist()
    g = lt.tolist()
    hits, cnt = 0.0, 0
    for i in range(len(p)):
        for j in range(i + 1, len(p)):
            dy = g[i] - g[j]
            if dy == 0:
                continue
            cnt += 1
            d = p[i] - p[j]
            hits += 0.5 if d == 0 else (1.0 if d * dy > 0 else 0.0)
    a = np.asarray(p, dtype=np.float64)
    b = np.asarray(g, dtype=np.float64)
    pear = float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else float("nan")
    return {
        "n": len(ds),
        "mae4": float(mae_dims.mean()),
        "mae_dim": {k: float(mae_dims[i]) for i, k in enumerate(BRANCH_KEYS)},
        "pairwise": float(hits / cnt) if cnt else float("nan"),
        "pearson": pear,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="data/synthetic/index.json")
    ap.add_argument("--teacher", default="checkpoints/distill/teacher/best.pt")
    ap.add_argument("--steps", type=int, default=6000)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--lr-final", type=float, default=3e-5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--eval-interval", type=int, default=250)
    ap.add_argument("--kd-sub", type=float, default=1.0, help="teacher sub-score MSE weight")
    ap.add_argument("--kd-total", type=float, default=1.0, help="teacher total MSE weight")
    ap.add_argument("--reg", type=float, default=1.0, help="ground-truth reg weight")
    ap.add_argument("--mae-target", type=float, default=5.0)
    ap.add_argument("--init-from-teacher", action="store_true", default=True)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)

    train_ds = load_split(args.source, "train")
    val_ds = load_split(args.source, "val")
    print(f"[goal1] train={len(train_ds)} val={len(val_ds)}", flush=True)

    # 学生 = 教师同宽度（376,594 参数，远低于 10M 预算，无需剪枝）
    student = teacher()
    n_params = sum(p.numel() for p in student.parameters())
    print(f"[goal1] student params={n_params:,} (budget 10,000,000)", flush=True)

    teacher_model = teacher()
    tb = torch.load(args.teacher, map_location="cpu", weights_only=False)
    teacher_model.load_state_dict(tb["model"], strict=True)
    teacher_model.eval()
    for p in teacher_model.parameters():
        p.requires_grad_(False)

    if args.init_from_teacher:
        student.load_state_dict(tb["model"], strict=True)
        print("[goal1] init: teacher weights (distillation from identical arch)", flush=True)

    student.train()
    opt = tcli._optimizer(student)
    idx_cur = tcli._IndexCursor(len(train_ds), args.seed)

    best = {"mae4": float("inf")}
    best_state = None
    hist = []
    t0 = time.time()

    def lr_at(step):
        prog = step / max(args.steps, 1)
        return args.lr_final + 0.5 * (args.lr - args.lr_final) * (1.0 + math.cos(math.pi * prog))

    # step 0 eval: teacher-init baseline (证明起点，不训练也达标则不训练)
    m0 = eval_split(student, val_ds)
    hist.append({"step": 0, **m0})
    print(f"[goal1] step 0 (init) val mae4={m0['mae4']:.4f} pair={m0['pairwise']:.4f} pearson={m0['pearson']:.4f}", flush=True)
    if m0["mae4"] <= args.mae_target and m0["pairwise"] >= 0.68 and m0["pearson"] >= 0.70:
        best = {"step": 0, **m0}
        best_state = {k: v.detach().cpu().clone() for k, v in student.state_dict().items()}

    for step in range(1, args.steps + 1):
        for g in opt.param_groups:
            g["lr"] = lr_at(step)
        idxs = idx_cur.next_batch(args.batch)
        imgs, subs, tots = gather(train_ds, idxs)
        out = student(imgs, return_ranking=True)
        with torch.no_grad():
            tout = teacher_model(imgs, return_ranking=False)
        pred_sub = torch.cat([out[k] for k in BRANCH_KEYS], dim=-1)
        t_sub = torch.cat([tout[k] for k in BRANCH_KEYS], dim=-1)
        l_kd_sub = (pred_sub - t_sub).pow(2).mean()
        l_kd_total = (out["total"].reshape(-1) - tout["total"].reshape(-1)).pow(2).mean()
        l_reg = tcli.regression_loss(out, tots, subs)
        loss = args.kd_sub * l_kd_sub + args.kd_total * l_kd_total + args.reg * l_reg
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()

        if step % args.eval_interval == 0 or step == args.steps:
            m = eval_split(student, val_ds)
            hist.append({"step": step, **m})
            print(
                f"[goal1] step {step}/{args.steps} loss={float(loss.detach()):.4f} "
                f"val mae4={m['mae4']:.4f} pair={m['pairwise']:.4f} pearson={m['pearson']:.4f}",
                flush=True,
            )
            if m["mae4"] < best["mae4"]:
                best = {"step": step, **m}
                best_state = {k: v.detach().cpu().clone() for k, v in student.state_dict().items()}
                torch.save(
                    {"schema_version": 1, "step": step, "model": best_state,
                     "config": {"arch": "teacher-width", "params": n_params,
                                "kd_sub": args.kd_sub, "kd_total": args.kd_total,
                                "reg": args.reg, "lr": args.lr, "seed": args.seed},
                     "val_metrics": m},
                    OUT_DIR / "best.pt",
                )
            if m["mae4"] <= args.mae_target and m["pairwise"] >= 0.68 and m["pearson"] >= 0.70:
                print(f"[goal1] TARGET MET at step {step}: mae4={m['mae4']:.4f} <= {args.mae_target}", flush=True)
                break

    elapsed = round(time.time() - t0, 1)
    # 用最优权重评 test（诚实：test 只在最终一次性评估，不参与选择）
    if best_state is not None:
        student.load_state_dict(best_state, strict=True)
    test_ds = load_split(args.source, "test")
    test_m = eval_split(student, test_ds)

    report = {
        "approach": "no-prune teacher-width KD distillation (S6-01 budget 10M not binding)",
        "student_params": n_params,
        "budget": 10_000_000,
        "params_within_budget": n_params < 10_000_000,
        "hyper": {"kd_sub": args.kd_sub, "kd_total": args.kd_total, "reg": args.reg,
                  "steps": args.steps, "lr": args.lr, "seed": args.seed},
        "best_val": best,
        "test": test_m,
        "history": hist,
        "elapsed_s": elapsed,
        "gates": {"mae4_max": args.mae_target, "pairwise_min": 0.68, "pearson_min": 0.70},
        "val_pass": best.get("mae4", 9e9) <= args.mae_target and best.get("pairwise", 0) >= 0.68 and best.get("pearson", 0) >= 0.70,
        "test_pass": test_m["mae4"] <= args.mae_target and test_m["pairwise"] >= 0.68 and test_m["pearson"] >= 0.70,
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("student_params", "params_within_budget", "best_val", "test", "val_pass", "test_pass", "elapsed_s")}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
