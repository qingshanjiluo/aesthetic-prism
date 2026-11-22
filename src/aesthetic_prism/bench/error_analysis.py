"""Stage-7 error analysis data: low-score / high-divergence sample attribution.

Writes reports/error_analysis_data.json for ERROR_ANALYSIS.md.
"""
import json
import os
import pathlib

import numpy as np
import onnxruntime as ort

ROOT = os.environ.get("AP_ROOT") or os.getcwd()
os.chdir(ROOT)
SEED = 42
KEYS = ["total", "composition", "light", "creativity", "story"]
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def load_image(path):
    from PIL import Image
    img = Image.open(path).convert("RGB").resize((224, 224), Image.BILINEAR)
    a = np.asarray(img, dtype=np.float32) / 255.0
    a = (a - MEAN) / STD
    return np.transpose(a, (2, 0, 1))[None]


def main():
    idx = json.loads(pathlib.Path(os.path.join("data", "synthetic", "index.json")).read_text(encoding="utf-8"))["samples"]
    sess = ort.InferenceSession(os.path.join("artifacts", "student.onnx"), providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(SEED)
    picks = rng.permutation(len(idx))[:60]
    rows = []
    for i in picks:
        s = idx[i]
        g = s["labels"]
        gt_total = g.get("total", float(np.mean([g[d] for d in KEYS[1:]])))
        out = sess.run(None, {"images": load_image(s["image_path"])})
        pred = {k: float(out[j][0][0]) for j, k in enumerate(KEYS)}
        err = {k: abs(pred[k] - g[k]) for k in KEYS[1:]}
        rows.append({
            "id": s["id"], "source": s.get("source"),
            "gt": {k: float(g[k]) for k in KEYS[1:]}, "gt_total": gt_total,
            "pred": pred, "abs_err": err,
            "mae4": float(np.mean(list(err.values()))),
        })
    by_mae = sorted(rows, key=lambda r: -r["mae4"])
    low = sorted(rows, key=lambda r: r["gt_total"])[:10]
    out = {
        "n_eval": len(rows),
        "worst10_by_mae4": by_mae[:10],
        "lowest_gt_total_10": low,
        "per_dim_mae": {k: float(np.mean([r["abs_err"][k] for r in rows])) for k in KEYS[1:]},
        "pred_std": {k: float(np.std([r["pred"][k] for r in rows])) for k in KEYS[1:]},
        "label_std": {k: float(np.std([r["gt"][k] for r in rows])) for k in KEYS[1:]},
    }
    pathlib.Path(os.path.join("reports", "error_analysis_data.json")).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("per_dim_mae", out["per_dim_mae"])
    print("pred_std", out["pred_std"])
    print("label_std", out["label_std"])
    print("worst", [(r["id"], round(r["mae4"], 1)) for r in by_mae[:10]])


if __name__ == "__main__":
    main()
