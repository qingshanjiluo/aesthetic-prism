"""Contract test: exported ONNX graphs match frozen C-EXPORT-01 (onnx_io_names.md).

Validates artifacts/student.onnx (primary deliverable) and, when present,
models/hapnet_teacher.onnx (shared IO contract).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from aesthetic_prism.export.onnx_export import (
    INPUT_NAME,
    OUTPUT_NAMES,
    load_session,
    run_session,
)

REPO = Path(__file__).resolve().parents[2]
STUDENT_ONNX = REPO / "artifacts" / "student.onnx"
TEACHER_ONNX = REPO / "models" / "hapnet_teacher.onnx"


def _assert_contract(path: Path) -> None:
    sess = load_session(path)  # raises OnnxSchemaError on any IO mismatch
    inp = sess.get_inputs()[0]
    assert inp.name == INPUT_NAME
    shape = inp.shape
    assert shape[0] in (None, "batch", "N"), f"batch dim not dynamic: {shape}"
    assert shape[1:] == [3, 224, 224], f"H/W must be fixed 224: {shape}"
    outs = sess.get_outputs()
    assert [o.name for o in outs] == list(OUTPUT_NAMES)
    for o in outs:
        assert o.shape[0] in (None, "batch", "N")
        assert o.shape[1:] == [1]

    rng = np.random.default_rng(0)
    for n in (1, 4):
        batch = rng.standard_normal((n, 3, 224, 224)).astype("float32")
        result = run_session(sess, batch)
        assert list(result.keys()) == list(OUTPUT_NAMES)
        for name, arr in result.items():
            assert arr.shape == (n, 1)
            assert arr.dtype == np.float32
            assert float(arr.min()) >= 0.0 and float(arr.max()) <= 100.0, (
                f"{path.name}:{name} out of [0,100]: {arr.min()}..{arr.max()}"
            )


def test_onnx_io_matches_contract() -> None:
    if not STUDENT_ONNX.exists():
        pytest.fail(
            "artifacts/student.onnx missing — run the distill pipeline "
            "(python -m aesthetic_prism.distill --source data/synthetic/index.json)"
        )
    _assert_contract(STUDENT_ONNX)
    if TEACHER_ONNX.exists():
        _assert_contract(TEACHER_ONNX)
