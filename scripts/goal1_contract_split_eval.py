"""按契约 C-DATA-01 §2.2 口径（split_of, sha256%20）复测 teacher + student。
背景：src/aesthetic_prism/bench/metric_recheck.py 用的是「按 id 排序后按序号切 10%/10%」，
与契约 split_of 口径不同 → 165 train / 19 val / 16 test（契约）vs 160/20/20（序号）。
本脚本用契约口径给出正确的 val/test 指标。
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

from aesthetic_prism.data.schema import split_of

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
DIMS = ("composition", "light", "creativity", "story")
MODELS = {"teacher": "models/hapnet_teacher.onnx", "student": "artifacts/student.onnx"}


def preprocess(path):
    img = Image.open(path).convert("RGB").resize((224, 224), Image.BILINEAR)
    a = np.asarray(img, dtype=np.float32) / 255.0
    a = (a - MEAN) / STD
    return np.transpose(a, (2, 0, 1))[None].astype(np.float32)


def pairwise(p, g):
    hits, cnt = 0.0, 0
    for i in range(len(p)):
        for j in range(i + 1, len(p)):
            dy = g[i] - g[j]
            if dy == 0:
                continue
            cnt += 1
            d = p[i] - p[j]
            hits += 0.5 if d == 0 else (1.0 if d * dy > 0 else 0.0)
    return hits / cnt if cnt else float("nan")


def pearson(a, b):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def main():
    idx = json.loads(pathlib.Path("data/synthetic/index.json").read_text(encoding="utf-8"))
    samples = idx["samples"]
    buckets = {"train": [], "val": [], "test": []}
    for s in samples:
        buckets[split_of(s["id"])].append(s)
    print(f"contract split_of counts: train={len(buckets['train'])} val={len(buckets['val'])} test={len(buckets['test'])}")

    feats = {sp: [preprocess(os.path.join(".", s["image_path"])) for s in buckets[sp]] for sp in ("val", "test")}
    out = {"split_definition": "C-DATA-01 §2.2 split_of (sha256%20)", "counts": {k: len(v) for k, v in buckets.items()}, "models": {}}

    for name, path in MODELS.items():
        if not os.path.exists(path):
            continue
        sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        res = {}
        for sp in ("val", "test"):
            Ps, Gs, pt, gt = [], [], [], []
            for x, s in zip(feats[sp], buckets[sp]):
                r = sess.run(None, {"images": x})
                lab = s["labels"]
                Ps.append([float(r[1 + i][0][0]) for i in range(4)])
                Gs.append([float(lab[k]) for k in DIMS])
                pt.append(float(r[0][0][0]))
                gt.append(float(lab["total"]))
            Ps, Gs = np.array(Ps), np.array(Gs)
            mae_dims = np.abs(Ps - Gs).mean(axis=0)
            res[sp] = {
                "n": len(Ps),
                "mae4": round(float(mae_dims.mean()), 6),
                "mae_dim": {DIMS[d]: round(float(mae_dims[d]), 4) for d in range(4)},
                "pairwise": round(pairwise(pt, gt), 6),
                "pearson": round(pearson(pt, gt), 6),
                "gate_mae4_pass": bool(mae_dims.mean() <= 5.0),
                "gate_pairwise_pass": bool(pairwise(pt, gt) >= 0.68),
                "gate_pearson_pass": bool(pearson(pt, gt) >= 0.70),
            }
        out["models"][name] = res
        print(f"\n[{name}]")
        for sp in ("val", "test"):
            r = res[sp]
            print(f"  {sp} n={r['n']} mae4={r['mae4']:.4f} pair={r['pairwise']:.4f} pearson={r['pearson']:.4f} "
                  f"mae4_pass={r['gate_mae4_pass']}")

    pathlib.Path("reports/contract_split_metrics.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("\nwrote reports/contract_split_metrics.json")


if __name__ == "__main__":
    main()
