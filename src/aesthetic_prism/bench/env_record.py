"""T-6-05: environment record — versions, seed, model checksums, run commands."""
import hashlib
import json
import os
import pathlib
import platform
import sys

import numpy as np
import onnx
import onnxruntime as ort
import PIL

ROOT = os.environ.get("AP_ROOT") or os.getcwd()
os.chdir(ROOT)


def sha256(p, limit=1024 * 1024):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        h.update(f.read(limit))
    return h.hexdigest()


def main():
    rec = {
        "python": sys.version,
        "platform": platform.platform(),
        "onnx": onnx.__version__,
        "onnxruntime": ort.__version__,
        "numpy": np.__version__,
        "pillow": PIL.__version__,
        "model_files": {
            "artifacts/student.onnx": {"bytes": os.path.getsize("artifacts/student.onnx"), "sha256_1MB": sha256("artifacts/student.onnx")},
            "artifacts/student_int8.onnx": {"bytes": os.path.getsize("artifacts/student_int8.onnx"), "sha256_1MB": sha256("artifacts/student_int8.onnx")},
            "models/hapnet_teacher.onnx": {"bytes": os.path.getsize("models/hapnet_teacher.onnx"), "sha256_1MB": sha256("models/hapnet_teacher.onnx")},
        },
        "frozen_kd_constants": {
            "steps": 3000, "kd_lr": "1e-4->1e-5", "kd_batch": 32, "tau": 10.0,
            "alpha": 0.3, "joint_from": 4200, "seed": 42,
        },
        "prune_widths": {"stem": 20, "trunk": 77, "branch_feat_dim": 39, "gate_hidden": 77, "ranking_hidden": 77},
        "student_params": 147032,
        "commands": {
            "quantize": "python src/aesthetic_prism/bench/quantize_int8.py",
            "bench": "python src/aesthetic_prism/bench/bench_latency.py",
            "recheck": "python src/aesthetic_prism/bench/metric_recheck.py",
            "calibrate": "python src/aesthetic_prism/bench/metric_calibrate.py",
        },
    }
    pathlib.Path(os.path.join("reports", "env_record.json")).write_text(json.dumps(rec, indent=2), encoding="utf-8")
    print(json.dumps(rec, indent=2))


if __name__ == "__main__":
    main()
