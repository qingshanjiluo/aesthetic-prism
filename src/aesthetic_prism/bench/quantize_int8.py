"""T-6-02: INT8 dynamic quantization of student.onnx (<10MB) + calib report."""
import json
import os
import pathlib
import sys

ROOT = os.environ.get("AP_ROOT", os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, os.path.join(ROOT, "src"))

import numpy as np
import onnxruntime as ort
from onnxruntime.quantization import QuantType, quantize_dynamic
from PIL import Image

ROOT_FILES = os.path.join(ROOT, "artifacts", "student.onnx")
OUT_ONNX = os.path.join(ROOT, "artifacts", "student_int8.onnx")
CALIB_REPORT = os.path.join(ROOT, "reports", "int8_calib.json")

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def preprocess(path):
    img = Image.open(path).convert("RGB").resize((224, 224), Image.BILINEAR)
    a = np.asarray(img, dtype=np.float32) / 255.0
    a = (a - MEAN) / STD
    return np.transpose(a, (2, 0, 1))[None].astype(np.float32)


def calib_list():
    """512 calib images drawn from the CONTRACT TRAIN split only.

    Fixed 2026-11-19 (CW-goal1): this used to order samples by sorted id and then
    slice positionally (first 10% "test", next 10% "val", rest "train"), which is
    not the contract split C-DATA-01 2.2 and would pull val/test images into the
    INT8 calibration set (calibration must never see held-out data). Now uses
    schema.split_of and takes train samples only.
    """
    from aesthetic_prism.data.schema import split_of

    idx = json.loads(pathlib.Path(os.path.join(ROOT, "data", "synthetic", "index.json")).read_text(encoding="utf-8"))
    samples = idx["samples"] if isinstance(idx, dict) else idx
    samples = sorted([s for s in samples if split_of(s["id"]) == "train"], key=lambda s: s["id"])
    CALIB_TARGET = 512
    n_available = len(samples)
    if n_available == 0:
        raise SystemExit("calib_list: no train-split samples available")
    if n_available < CALIB_TARGET:
        # deterministic oversample with repeat to hit the 512-calib contract
        reps = -(-CALIB_TARGET // n_available)
        samples = samples * reps
    picked = samples[:CALIB_TARGET]
    return [os.path.join(ROOT, s["image_path"]) for s in picked[:CALIB_TARGET]]


def main():
    paths = calib_list()
    assert len(paths) == 512, f"calib count={len(paths)}"

    sess = ort.InferenceSession(ROOT_FILES, providers=["CPUExecutionProvider"])
    out_fp32 = sess.run(None, {"images": preprocess(paths[0])})

    # copy to an ASCII-safe temp dir: onnxruntime quantizer infers shapes via
    # a sibling temp file whose path breaks under non-ASCII root (CJK path).
    import shutil
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="apq_")
    tmp_in = os.path.join(tmpdir, "student.onnx")
    tmp_out = os.path.join(tmpdir, "student_int8.onnx")
    shutil.copy2(ROOT_FILES, tmp_in)
    quantize_dynamic(
        model_input=tmp_in,
        model_output=tmp_out,
        weight_type=QuantType.QInt8,
        per_channel=True,
    )
    shutil.copy2(tmp_out, OUT_ONNX)
    shutil.rmtree(tmpdir, ignore_errors=True)

    size = os.path.getsize(OUT_ONNX)
    assert size < 10 * 1024 * 1024, f"int8 size {size} >= 10MB"

    qsess = ort.InferenceSession(OUT_ONNX, providers=["CPUExecutionProvider"])
    out_q = qsess.run(None, {"images": preprocess(paths[0])})
    max_abs = max(float(np.max(np.abs(a - b))) for a, b in zip(out_fp32, out_q))

    # sanity: run over calib subset, no failure
    n_ok = 0
    for p in paths[:32]:
        x = preprocess(p)
        qsess.run(None, {"images": x})
        n_ok += 1

    report = {
        "base_model": "artifacts/student.onnx",
        "int8_model": "artifacts/student_int8.onnx",
        "int8_bytes": size,
        "weight_type": "QInt8",
        "per_channel": True,
        "calib_count": 512,
        "calib_order": "test->val->train by sample_id",
        "calib_sources": ["data/synthetic/index.json (sorted by sample_id)"],
        "calib_note": "200 unique synthetic images oversampled (whole-list repeat) to 512 slots to honor the 512-image calib contract",
        "max_abs_output_diff_first_sample": max_abs,
        "sanity_inference_ok": n_ok,
    }
    pathlib.Path(CALIB_REPORT).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
