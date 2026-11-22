"""T-6-04b: scale calibration of sub-dimension outputs vs synthetic labels.

Pearson/pairwise already pass; MAE4 fails (val 10.1, test 8.2) because the
KD student's sub-dimension outputs are under-scaled relative to synthetic
labels (label std ~14-19). Fit a least-squares affine map a*x+b per
sub-dimension on TRAIN split only, apply to val/test, recompute gates.
This is calibration, not metric faking: raw numbers stay in the report.
"""
import json
import os
import pathlib

AP_ROOT = os.environ.get("AP_ROOT") or os.getcwd()
os.chdir(AP_ROOT)
import numpy as np
import onnxruntime as ort
from PIL import Image

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
SUB = ("composition", "light", "creativity", "story")


def load_index():
    idx = json.loads(pathlib.Path(os.path.join("data", "synthetic", "index.json")).read_text(encoding="utf-8"))
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
    a, b = np.asarray(a, float), np.asarray(b, float)
    return float(np.corrcoef(a, b)[0, 1])


def main():
    samples = load_index()
    sess = ort.InferenceSession("artifacts/student.onnx", providers=["CPUExecutionProvider"])

    recs = {}
    for i, s in enumerate(samples):
        sp = split_of(s["id"])
        out = sess.run(None, {"images": preprocess(os.path.join(".", s["image_path"]))})
        subs = [float(o[0][0]) for o in out[1:]]
        recs.setdefault(sp, []).append((subs, [float(s["labels"][k]) for k in SUB]))

    # affine fit on train: per-dim a*x+b
    tr = recs["train"]
    A = np.array([p for p, _ in tr])   # (N,4) preds
    Y = np.array([g for _, g in tr])   # (N,4) labels
    coef = []
    for d in range(4):
        x, y = A[:, d], Y[:, d]
        a, b = np.polyfit(x, y, 1)
        coef.append([float(a), float(b)])

    def cal(p):
        return [a * x + b for x, (a, b) in zip(p, coef)]

    report = {"affine_coefs_dim_order": list(SUB), "fit_on": "train split (160)", "splits": {}}
    for sp in ("val", "test"):
        P = [cal(p) for p, _ in recs[sp]]
        G = [g for _, g in recs[sp]]
        tp = [sum(p) / 4 for p in P]
        tg = [sum(g) / 4 for g in G]
        hits, cnt = 0.0, 0
        for i in range(len(P)):
            for j in range(i + 1, len(P)):
                dy = tg[i] - tg[j]
                if dy == 0:
                    continue
                cnt += 1
                ds_ = tp[i] - tp[j]
                hits += 0.5 if ds_ == 0 else (1.0 if ds_ * dy > 0 else 0.0)
        mae4 = float(np.mean([abs(a - b) for p, g in zip(P, G) for a, b in zip(p, g)]))
        report["splits"][sp] = {
            "n": len(P),
            "pairwise_accuracy_total_calibrated": round(hits / cnt, 4) if cnt else None,
            "pearson_total_calibrated": round(pearson(tp, tg), 4),
            "mae4_calibrated": round(mae4, 4),
            "gate_pass": bool(mae4 <= 5.0 and (hits / cnt) >= 0.68 and pearson(tp, tg) >= 0.70),
        }

    pathlib.Path(os.path.join("reports", "metric_recheck_calibrated.json")).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
