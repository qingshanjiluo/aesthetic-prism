"""mae4 误差分解（goal ① 诊断）：逐维 MAE / 偏置 / 尺度斜率 / 饱和率。
目的：判定 mae4=8.196 是「某一维崩」还是「四维普遍收缩」，为修复路径定方向。
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
import onnxruntime as ort
from PIL import Image

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
DIMS = ("composition", "light", "creativity", "story")
SESS = None


def load_index():
    idx = json.loads(pathlib.Path("data/synthetic/index.json").read_text(encoding="utf-8"))
    return sorted(idx["samples"], key=lambda s: s["id"])


def split_of(sample_id: str) -> str:
    """Contract split (C-DATA-01 2.2) — sha256(id)[:8] % 20.

    Fixed 2026-11-19: an earlier positional split (first 10% test, next 10% val
    over id-sorted order) did NOT match the split training used, which leaked
    every positional test sample into the contract train split.
    """
    import hashlib

    v = int(hashlib.sha256(sample_id.encode("utf-8")).hexdigest()[:8], 16) % 20
    return "train" if v < 16 else ("val" if v < 18 else "test")


def preprocess(path):
    img = Image.open(path).convert("RGB").resize((224, 224), Image.BILINEAR)
    a = np.asarray(img, dtype=np.float32) / 255.0
    a = (a - MEAN) / STD
    return np.transpose(a, (2, 0, 1))[None].astype(np.float32)


def infer_all(samples):
    out = {"train": [], "val": [], "test": []}
    for i, s in enumerate(samples):
        sp = split_of(s["id"])
        x = preprocess(os.path.join(".", s["image_path"]))
        r = SESS.run(None, {"images": x})
        total = float(r[0][0][0])
        subs = [float(o[0][0]) for o in r[1:]]
        lab = s["labels"]
        gt = {k: float(lab[k]) for k in DIMS}
        gt_total = float(lab.get("total", sum(gt.values()) / 4.0))
        out[sp].append({"pred_total": total, "pred": subs, "gt": [gt[k] for k in DIMS],
                        "gt_total": gt_total, "path": s["image_path"]})
    return out


def stats(P):
    pred = np.array([p["pred"] for p in P], dtype=np.float64)      # (n,4)
    gt = np.array([p["gt"] for p in P], dtype=np.float64)          # (n,4)
    res = {}
    mae_dims = np.abs(pred - gt).mean(axis=0)
    bias_dims = (pred - gt).mean(axis=0)
    slope_dims, sat = [], []
    for d in range(4):
        if gt[:, d].std() > 1e-9:
            slope = float(np.polyfit(gt[:, d], pred[:, d], 1)[0])
        else:
            slope = float("nan")
        slope_dims.append(slope)
        sat.append(float(((pred[:, d] < 1.0) | (pred[:, d] > 99.0)).mean()))
    res["per_dim"] = {
        DIMS[d]: {
            "mae": round(float(mae_dims[d]), 4),
            "bias": round(float(bias_dims[d]), 4),
            "scale_slope": round(slope_dims[d], 4),
            "sat_rate": round(sat[d], 4),
            "gt_std": round(float(gt[:, d].std()), 4),
            "pred_std": round(float(pred[:, d].std()), 4),
        }
        for d in range(4)
    }
    # 总 MAE 的逐维贡献（等权平均 → 每维贡献 = mae/4）
    contrib = {DIMS[d]: round(float(mae_dims[d]) / 4.0, 4) for d in range(4)}
    tot = float(mae_dims.mean())
    res["mae4"] = round(tot, 6)
    res["contribution"] = contrib
    res["dominant_dim"] = max(contrib, key=contrib.get)
    # 若把主导维的预测替换为真值（即该维完美），mae4 会降到多少
    best_d = DIMS.index(res["dominant_dim"])
    fixed = np.abs(pred - gt).copy()
    fixed[:, best_d] = 0.0
    res["mae4_if_dominant_perfect"] = round(float(fixed.mean()), 4)
    # 只做逐维去偏置（bias 减掉）后的 mae4
    debiased = np.abs((pred - bias_dims) - gt)
    res["mae4_after_debias"] = round(float(debiased.mean()), 4)
    # 逐维 affine(用本 split 拟合，仅作上限参考，非可用方案)
    aff = np.zeros_like(pred)
    for d in range(4):
        k, b = np.polyfit(gt[:, d], pred[:, d], 1)
        aff[:, d] = k * gt[:, d] + b
    res["mae4_oracle_affine"] = round(float(np.abs(aff - gt).mean()), 4)
    return res


def main():
    global SESS
    SESS = ort.InferenceSession("artifacts/student.onnx", providers=["CPUExecutionProvider"])
    samples = load_index()
    data = infer_all(samples)
    report = {sp: {"n": len(data[sp]), **stats(data[sp])} for sp in ("val", "test")}

    # train 上拟合 per-dim affine，再应用到 val/test（诚实：不偷看 val/test）
    tr = data["train"]
    ptr = np.array([p["pred"] for p in tr], dtype=np.float64)
    gtr = np.array([p["gt"] for p in tr], dtype=np.float64)
    coef = {}
    for d in range(4):
        k, b = np.polyfit(gtr[:, d], ptr[:, d], 1)
        coef[DIMS[d]] = {"k": float(k), "b": float(b)}
    cal = {}
    for sp in ("val", "test"):
        Pp = np.array([p["pred"] for p in data[sp]], dtype=np.float64)
        Gg = np.array([p["gt"] for p in data[sp]], dtype=np.float64)
        fixed = np.stack([
            (Pp[:, d] - coef[DIMS[d]]["b"]) / coef[DIMS[d]]["k"]
            if abs(coef[DIMS[d]]["k"]) > 1e-6 else Pp[:, d]
            for d in range(4)
        ], axis=1)
        cal[sp] = round(float(np.abs(fixed - Gg).mean()), 4)

    out = {
        "model": "artifacts/student.onnx",
        "diagnosis": report,
        "train_fitted_affine_coef": coef,
        "mae4_after_train_affine": cal,
    }
    pathlib.Path("reports/mae4_decomposition.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
