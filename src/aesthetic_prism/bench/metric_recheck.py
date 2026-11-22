"""T-6-04: metric re-check of the exported student.onnx on VAL + TEST splits.

Gates (03 section 5.3 / 00_PRD AC3): pairwise>=0.68, Pearson(total)>=0.70,
MAE<=5.0. Uses the training evaluate() for split-consistent metrics, plus
Pearson computed here. Honest record: distill_report.json stage2/3 already
shows the 147k student below gate on the 19-sample val split; we re-measure
and record the real numbers.

SPLIT DEFINITION (fixed 2026-11-19, CW-goal1): must use the contract
C-DATA-01 section 2.2 split_of(sample_id) = sha256(id)[:8] % 20 <16 train /
<18 val / else test. An earlier version of this file split by "sorted index
position" (first 10% test, next 10% val), which does NOT match the definition
training used: every one of those 20 "test" samples belongs to the contract
TRAIN split, so the reported test metrics were measured on training data
(leakage -> inflated to mae4 8.196 / pairwise 0.956). Real contract-split
numbers are far worse; they are what this script must report.
"""
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


def load_index():
    idx = json.loads(pathlib.Path(os.path.join("data", "synthetic", "index.json")).read_text(encoding="utf-8"))
    return sorted(idx["samples"], key=lambda s: s["id"])


def split_index(sample_id: str) -> str:
    """Contract split (C-DATA-01 2.2) — sha256(id)[:8] % 20; NOT positional."""
    return split_of(sample_id)


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


def main():
    samples = load_index()
    sess = ort.InferenceSession("artifacts/student.onnx", providers=["CPUExecutionProvider"])

    preds, gts = {"test": [], "val": [], "train": []}, {"test": [], "val": [], "train": []}
    for s in samples:
        sp = split_index(s["id"])
        x = preprocess(os.path.join(".", s["image_path"]))
        out = sess.run(None, {"images": x})
        total = float(out[0][0][0])
        subs = [float(o[0][0]) for o in out[1:]]
        labels = s["labels"]
        gt_total = float(labels.get("total", sum(labels[k] for k in ("composition", "light", "creativity", "story")) / 4.0))
        preds[sp].append((total, subs))
        gts[sp].append((gt_total, [float(labels[k]) for k in ("composition", "light", "creativity", "story")]))

    report = {}
    for sp in ("val", "test"):
        P, G = preds[sp], gts[sp]
        if not P:
            continue
        totals_p = [p[0] for p in P]
        totals_g = [g[0] for g in G]
        # pairwise accuracy on total (ties excluded, pred tie=0.5)
        hits, cnt = 0.0, 0
        for i in range(len(P)):
            for j in range(i + 1, len(P)):
                dy = totals_g[i] - totals_g[j]
                if dy == 0:
                    continue
                cnt += 1
                ds_ = totals_p[i] - totals_p[j]
                hits += 0.5 if ds_ == 0 else (1.0 if ds_ * dy > 0 else 0.0)
        pa = hits / cnt if cnt else float("nan")
        # MAE over 4 sub dims
        diffs = []
        for (tp, sp4), (tg, sg4) in zip(P, G):
            diffs.extend(abs(a - b) for a, b in zip(sp4, sg4))
        mae4 = sum(diffs) / len(diffs)
        report[sp] = {
            "n": len(P),
            "pairwise_accuracy_total": float(pa),
            "pearson_total": float(pearson(totals_p, totals_g)),
            "mae4": float(mae4),
        }

    gates = {
        "pairwise_min": 0.68,
        "pearson_min": 0.70,
        "mae4_max": 5.0,
    }
    for sp, r in report.items():
        r["gate_pairwise_pass"] = r["pairwise_accuracy_total"] >= gates["pairwise_min"]
        r["gate_pearson_pass"] = r["pearson_total"] >= gates["pearson_min"]
        r["gate_mae_pass"] = r["mae4"] <= gates["mae4_max"]
        r["gate_pass"] = r["gate_pairwise_pass"] and r["gate_pearson_pass"] and r["gate_mae_pass"]

    out = {"model": "artifacts/student.onnx", "gates": gates, "splits": report}
    pathlib.Path(os.path.join("reports", "metric_recheck.json")).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
