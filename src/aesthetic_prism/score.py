"""Single-image scoring CLI: python -m aesthetic_prism.score <image_path> ...

Loads artifacts/student.onnx via the C-EXPORT-01 loader, runs a real
onnxruntime inference on the image(s), and prints one JSON object with six
fields: total / composition / light / creativity / story / model.

Usage:
  PYTHONPATH=src python -m aesthetic_prism.score path/to/image.jpg
  PYTHONPATH=src python -m aesthetic_prism.score img1.jpg img2.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from aesthetic_prism.export.onnx_export import (
    OUTPUT_NAMES,
    load_session,
    run_session,
)

DEFAULT_MODEL = Path(__file__).resolve().parents[2] / "artifacts" / "student.onnx"
INPUT_SIZE = 224
# ImageNet-ish normalization used by the training pipeline (dataset transform).
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _load_image(path: Path) -> np.ndarray:
    """Read an image file -> (3, 224, 224) float32 CHW, normalized."""
    if not path.exists():
        raise FileNotFoundError(f"image not found: {path}")
    from PIL import Image  # deferred: only needed at scoring time

    img = Image.open(path).convert("RGB").resize((INPUT_SIZE, INPUT_SIZE))
    arr = np.asarray(img, dtype=np.float32) / 255.0  # HWC [0,1]
    arr = (arr - _MEAN) / _STD
    return np.ascontiguousarray(arr.transpose(2, 0, 1))  # CHW


def score_images(paths: list[Path], model_path: Path) -> list[dict[str, object]]:
    """Real inference: onnxruntime session over the C-EXPORT-01 graph."""
    sess = load_session(model_path)
    batch = np.stack([_load_image(p) for p in paths]).astype(np.float32)
    result = run_session(sess, batch)
    n = batch.shape[0]
    scores: list[dict[str, object]] = []
    for i in range(n):
        item: dict[str, object] = {}
        for name in OUTPUT_NAMES:
            item[name] = round(float(result[name][i, 0]), 4)
        item["model"] = model_path.name  # real model identity, not mocked
        scores.append(item)
    return scores


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Score image(s) with the distilled student ONNX model"
    )
    p.add_argument("images", nargs="+", help="image file path(s)")
    p.add_argument("--model", default=str(DEFAULT_MODEL),
                   help="ONNX model path (default: artifacts/student.onnx)")
    args = p.parse_args(argv)
    model_path = Path(args.model)
    if not model_path.exists():
        print(
            f"model not found: {model_path} — run the distill pipeline first "
            f"(python -m aesthetic_prism.distill --source data/synthetic/index.json)",
            file=sys.stderr,
        )
        return 1
    results = score_images([Path(a) for a in args.images], model_path)
    print(json.dumps(results[0] if len(results) == 1 else results, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
