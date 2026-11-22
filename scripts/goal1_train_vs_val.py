"""关键诊断（round5）：训练集 vs 验证集 MAE。

此前所有分析都只测了 val，从未测过 train。这决定了根因是「信息上限」还是「优化/泛化」：
  - train MAE ≈ val MAE ≈ 11  →  模型连记忆都做不到 = 优化失败
  - train MAE << val MAE      →  过拟合 = 信息存在但没泛化
  - train MAE ≈ val MAE 且都显著低于"预测均值"基线 → 学到了部分可泛化信息

对 checkpoints/goal1v2/best.pt（round4 训练产物）与 artifacts/student.onnx 都测。
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
import torch
from PIL import Image

from aesthetic_prism.data.schema import split_of
from aesthetic_prism.model.model import BRANCH_KEYS, teacher

MEAN = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32).view(1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32).view(1, 3, 1, 1)
DIMS = BRANCH_KEYS


def load(split, samples, limit=None):
    ids = [s for s in samples if split_of(s["id"]) == split]
    if limit:
        ids = ids[:limit]
    imgs = torch.empty((len(ids), 3, 224, 224), dtype=torch.uint8)
    subs = torch.empty((len(ids), 4), dtype=torch.float32)
    for i, s in enumerate(ids):
        img = Image.open(os.path.join(".", s["image_path"])).convert("RGB").resize((224, 224), Image.BILINEAR)
        imgs[i] = torch.from_numpy(np.ascontiguousarray(np.asarray(img, dtype=np.uint8).transpose(2, 0, 1)))
        subs[i] = torch.tensor([float(s["labels"][k]) for k in DIMS])
    return imgs, subs


@torch.no_grad()
def eval_model(model, imgs, subs, bs=64):
    model.eval()
    ps = []
    for i in range(0, len(imgs), bs):
        x = (imgs[i:i + bs].float().div_(255.0) - MEAN) / STD
        out = model(x, return_ranking=False)
        ps.append(torch.cat([out[k] for k in BRANCH_KEYS], dim=-1))
    P = torch.cat(ps)
    mae_dims = (P - subs).abs().mean(dim=0)
    return {
        "n": len(imgs),
        "mae4": float(mae_dims.mean()),
        "mae_dim": {DIMS[i]: round(float(mae_dims[i]), 3) for i in range(4)},
        "pred_std": {DIMS[i]: round(float(P[:, i].std()), 3) for i in range(4)},
        "gt_std": {DIMS[i]: round(float(subs[:, i].std()), 3) for i in range(4)},
    }


def main():
    torch.set_num_threads(max(1, os.cpu_count() or 4))
    samples = json.loads(pathlib.Path("data/synthetic/index.json").read_text(encoding="utf-8"))["samples"]

    # 只取 train 的一个子集以控制时间（1603 张全量需约 3 分钟/模型）
    tr_i, tr_s = load("train", samples, limit=400)
    va_i, va_s = load("val", samples)
    print(f"train_subset={len(tr_i)} val={len(va_i)}", flush=True)

    # 基线：永远预测 train 均值
    mean_pred = tr_s.mean(dim=0)
    base = (mean_pred - va_s).abs().mean(dim=0)
    print(f"\n[基线] 恒预测 train 均值，val mae4 = {float(base.mean()):.4f}  "
          f"dims={ {DIMS[i]: round(float(base[i]),2) for i in range(4)} }", flush=True)

    out = {"baseline_mean_predictor_val_mae4": round(float(base.mean()), 4), "models": {}}

    ckpt_path = pathlib.Path("checkpoints/goal1v2/best.pt")
    if ckpt_path.exists():
        b = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        m = teacher()
        m.load_state_dict(b["model"], strict=True)
        r_tr = eval_model(m, tr_i, tr_s)
        r_va = eval_model(m, va_i, va_s)
        print(f"\n[checkpoint goal1v2/best.pt  step={b.get('step')}]", flush=True)
        print(f"  TRAIN mae4 = {r_tr['mae4']:.4f}   dims={r_tr['mae_dim']}", flush=True)
        print(f"  VAL   mae4 = {r_va['mae4']:.4f}   dims={r_va['mae_dim']}", flush=True)
        print(f"  TRAIN pred_std={r_tr['pred_std']}  gt_std={r_tr['gt_std']}", flush=True)
        print(f"  VAL   pred_std={r_va['pred_std']}", flush=True)
        gaps = r_va["mae4"] - r_tr["mae4"]
        print(f"  gap(val-train) = {gaps:+.4f}", flush=True)
        out["models"]["goal1v2_best"] = {
            "step": b.get("step"), "train": r_tr, "val": r_va, "gap": round(gaps, 4)}

    pathlib.Path("reports/train_vs_val.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nwrote reports/train_vs_val.json")


if __name__ == "__main__":
    main()
