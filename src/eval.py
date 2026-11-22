"""T-7-07 reproducibility recheck: regenerate metrics and compare against
reports/metric_recheck.json (tolerance 1e-6). Exit non-zero on mismatch.

Also used by `make reproduce` chain and S7-04 gate.
Usage: python -m src.eval --recheck --against reports/metric_recheck.json

SPLIT DEFINITION (fixed 2026-11-21): shares the contract split with
metric_recheck.py — C-DATA-01 section 2.2 split_of(sample_id) =
sha256(id)[:8] % 20 <16 train / <18 val / else test. The previous positional
split ("first 20 ids = test", "ids 20..39 = val") was inherited from an
earlier eval script that sorted by filename; every one of those 20 "test"
samples is contract-TRAIN, so this recheck compared contract-val/test numbers
against numbers measured on training data and could never converge. Both
sides now derive the split from the id, so the only remaining tolerance is
float determinism (1e-6).
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

SEED = 42
KEYS = ["total", "composition", "light", "creativity", "story"]
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
SPLITS = ("val", "test")
TOL = 1e-6


def load_image(path):
    img = Image.open(path).convert("RGB").resize((224, 224), Image.BILINEAR)
    a = np.asarray(img, dtype=np.float32) / 255.0
    a = (a - MEAN) / STD
    return np.transpose(a, (2, 0, 1))[None]


def bucketize(samples):
    """Contract split (C-DATA-01 2.2) — derived from id, never positional."""
    out = {sp: [] for sp in SPLITS}
    for i, s in enumerate(samples):
        sp = split_of(s["id"])
        if sp in out:
            out[sp].append(i)
    return out


def eval_split(sess, samples, ids):
    gt_t, pr_t, errs = [], [], []
    for i in ids:
        s = samples[i]
        g = s["labels"]
        gt_total = float(g.get("total", float(np.mean([g[d] for d in KEYS[1:]]))))
        out = sess.run(None, {"images": load_image(os.path.join(".", s["image_path"]))})
        pr_total = float(out[0][0][0])
        gt_t.append(gt_total)
        pr_t.append(pr_total)
        errs.append(np.mean([abs(float(out[j + 1][0][0]) - g[k]) for j, k in enumerate(KEYS[1:])]))
    gt = np.array(gt_t)
    pr = np.array(pr_t)
    n = len(gt)
    pw = float(np.mean([1.0 if (gt[i] - gt[j]) * (pr[i] - pr[j]) > 0 else 0.0
                        for i in range(n) for j in range(n) if gt[i] != gt[j]]))
    pear = float(np.corrcoef(gt, pr)[0, 1])
    return {"n": n, "pairwise_accuracy_total": pw, "pearson_total": pear, "mae4": float(np.mean(errs))}


def main():
    against = "reports/metric_recheck.json"
    if "--against" in sys.argv:
        against = sys.argv[sys.argv.index("--against") + 1]
    ref = json.loads(pathlib.Path(against).read_text(encoding="utf-8"))
    idx = json.loads(
        pathlib.Path(os.path.join("data", "synthetic", "index.json")).read_text(encoding="utf-8")
    )["samples"]
    sess = ort.InferenceSession(os.path.join("artifacts", "student.onnx"), providers=["CPUExecutionProvider"])

    buckets = bucketize(idx)
    for sp in SPLITS:
        print(f"split {sp} n={len(buckets[sp])} (contract sha256%20)")

    ok = True
    for split in SPLITS:
        m = eval_split(sess, idx, buckets[split])
        r = ref["splits"][split]
        if m["n"] != r.get("n"):
            print(f"{split}.n: recomputed={m['n']} recorded={r.get('n')} MISMATCH")
            ok = False
        for key in ("pairwise_accuracy_total", "pearson_total", "mae4"):
            diff = abs(m[key] - r[key])
            status = "OK" if diff <= TOL else "MISMATCH"
            if diff > TOL:
                ok = False
            print(f"{split}.{key}: recomputed={m[key]:.6f} recorded={r[key]:.6f} diff={diff:.2e} {status}")
    print("RECHECK-" + ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
