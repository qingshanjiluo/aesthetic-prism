"""教师/学生 mae4 对照：判定 mae4 超标的极限来源（教师容量 vs 蒸馏损失）。
对 models/hapnet_teacher.onnx 与 artifacts/student.onnx 用同一 split 口径评 val/test。
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
MODELS = {
    "teacher": "models/hapnet_teacher.onnx",
    "student": "artifacts/student.onnx",
}


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


def pearson(a, b):
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def pairwise(p, g):
    hits, cnt = 0.0, 0
    for i in range(len(p)):
        for j in range(i + 1, len(p)):
            dy = g[i] - g[j]
            if dy == 0:
                continue
            cnt += 1
            ds = p[i] - p[j]
            hits += 0.5 if ds == 0 else (1.0 if ds * dy > 0 else 0.0)
    return hits / cnt if cnt else float("nan")


def main():
    samples = load_index()
    paths = [(split_of(s["id"]), os.path.join(".", s["image_path"]), s["labels"]) for i, s in enumerate(samples)]
    feats = {}
    for sp, p, _ in paths:
        feats.setdefault(sp, []).append(preprocess(p))

    out = {}
    for name, onnx_path in MODELS.items():
        if not os.path.exists(onnx_path):
            out[name] = {"error": f"missing {onnx_path}"}
            continue
        sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        out_n = {k: list(v) for k, v in feats.items()}
        res = {}
        for sp in ("val", "test"):
            X = out_n[sp]
            labs = [lab for s, _, lab in paths if s == sp]
            P = {"total": [], "sub": []}
            G = {"total": [], "sub": []}
            for x, lab in zip(X, labs):
                r = sess.run(None, {"images": x})
                P["total"].append(float(r[0][0][0]))
                P["sub"].append([float(o[0][0]) for o in r[1:]])
                G["total"].append(float(lab.get("total", sum(float(lab[k]) for k in DIMS) / 4.0)))
                G["sub"].append([float(lab[k]) for k in DIMS])
            Ps = np.array(P["sub"], dtype=np.float64)
            Gs = np.array(G["sub"], dtype=np.float64)
            mae_dims = np.abs(Ps - Gs).mean(axis=0)
            res[sp] = {
                "n": len(X),
                "mae4": round(float(mae_dims.mean()), 4),
                "mae_dim": {DIMS[d]: round(float(mae_dims[d]), 3) for d in range(4)},
                "pairwise": round(pairwise(P["total"], G["total"]), 4),
                "pearson": round(pearson(P["total"], G["total"]), 4),
            }
        out[name] = res
    pathlib.Path("reports/teacher_student_mae.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
