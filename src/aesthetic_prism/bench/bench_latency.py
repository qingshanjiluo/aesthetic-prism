"""T-6-03: ORT latency benchmark, FP32 vs INT8, P50<=150ms P95<=500ms.

Note: dynamic quantization converts weights to int8 while MatMul inputs are
re-quantized per call; on some ORT builds int8 kernels here are slower than
fp32 for this tiny model, so we benchmark BOTH and gate on whichever deployment
variant is chosen; report records both. Gate: fp32 P50 (primary serve model).
"""
import json
import os
import pathlib
import time

import numpy as np
import onnxruntime as ort

ROOT = os.environ.get("AP_ROOT", ".")
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def bench(model_path, n=100, warmup=10):
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess = ort.InferenceSession(model_path, so, providers=["CPUExecutionProvider"])
    rng = np.random.default_rng(42)
    lat = []
    for i in range(n + warmup):
        x = rng.normal(0, 1, (1, 3, 224, 224)).astype(np.float32)
        t0 = time.perf_counter()
        sess.run(None, {"images": x})
        dt = (time.perf_counter() - t0) * 1000
        if i >= warmup:
            lat.append(dt)
    lat.sort()
    return {
        "model": os.path.relpath(model_path, ROOT),
        "n": n,
        "p50_ms": round(lat[len(lat) // 2], 3),
        "p95_ms": round(lat[int(len(lat) * 0.95)], 3),
        "max_ms": round(lat[-1], 3),
    }


def main():
    fp32 = os.path.join(ROOT, "artifacts", "student.onnx")
    int8 = os.path.join(ROOT, "artifacts", "student_int8.onnx")
    r_fp32 = bench(fp32)
    r_int8 = bench(int8)
    primary = r_fp32  # fp32 is the serving model; INT8 kept as artifact
    report = {
        "hardware": "CPU (CPUExecutionProvider, ORT_ENABLE_ALL)",
        "input": "1x3x224x224 fp32 random (seed=42)",
        "fp32": r_fp32,
        "int8": r_int8,
        "gate": "P50<=150ms P95<=500ms",
        "primary": primary,
        "gate_pass": primary["p50_ms"] <= 150 and primary["p95_ms"] <= 500,
    }
    out = os.path.join(ROOT, "reports", "latency.json")
    pathlib.Path(out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
