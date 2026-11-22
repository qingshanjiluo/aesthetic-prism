"""ONNX export/load/run contract implementation 鈥?C-EXPORT-01 (frozen).

Signatures are pinned by docs/contracts/onnx_io_names.md section 2 and must not
change. Export produces a pure-inference graph: 4 branches + fusion gate +
total head, 0-100 mapping in-graph, ranking head excluded (ScoreOnlyWrapper).
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import onnx
import torch
from torch import nn

from aesthetic_prism.model.heads import SCORE_KEYS, ScoreOnlyWrapper

INPUT_NAME: str = "images"
OUTPUT_NAMES: tuple[str, str, str, str, str] = (
    "total",
    "composition",
    "light",
    "creativity",
    "story",
)
OPSET: int = 17
INPUT_SHAPE: tuple[int | None, int, int, int] = (None, 3, 224, 224)
OUTPUT_SHAPE: tuple[int | None, int] = (None, 1)

DYNAMIC_AXES: dict[str, dict[int, str]] = {
    "images": {0: "batch"},
    "total": {0: "batch"},
    "composition": {0: "batch"},
    "light": {0: "batch"},
    "creativity": {0: "batch"},
    "story": {0: "batch"},
}


class OnnxExportError(RuntimeError):
    """torch.onnx.export failed / contract verification failed (C-EXPORT-01)."""


class OnnxSchemaError(ValueError):
    """Graph IO violates this contract (checked after load / at feed time)."""


class _TupleAdapter(nn.Module):
    """Wrap any scoring model into a tuple-output module named by OUTPUT_NAMES."""

    def __init__(self, model: nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(self, images: torch.Tensor) -> tuple[torch.Tensor, ...]:
        out = self.model(images)
        if isinstance(out, dict):
            missing = [k for k in SCORE_KEYS if k not in out]
            if missing:
                raise OnnxExportError(f"model output missing score keys {missing}")
            return tuple(out[k] for k in OUTPUT_NAMES)
        if isinstance(out, (tuple, list)):
            if len(out) != len(OUTPUT_NAMES):
                raise OnnxExportError(
                    f"model returned {len(out)} outputs, contract needs {len(OUTPUT_NAMES)}"
                )
            return tuple(out)
        raise OnnxExportError(f"unsupported model output type {type(out).__name__}")


def export_onnx(model: nn.Module, out_path: Path, opset: int = 17) -> dict[str, Any]:
    """Export the pure-inference graph per C-EXPORT-01 (signature frozen).

    model must be in eval(); the ranking head is excluded (ScoreOnlyWrapper).
    Returns metadata: {"opset", "input", "outputs", "ir_version", "path"}.
    """
    if model.training:
        raise ValueError("model must be in eval() before export")
    if opset != 17:
        raise OnnxExportError(f"opset must be 17 per contract C-EXPORT-01, got {opset}")
    out_path = Path(out_path)
    if not out_path.parent.exists():
        raise FileNotFoundError(f"output directory missing: {out_path.parent}")

    adapter = _TupleAdapter(ScoreOnlyWrapper(model) if not isinstance(model, ScoreOnlyWrapper) else model)
    adapter.eval()
    dummy = torch.zeros(1, 3, 224, 224, dtype=torch.float32)
    with torch.no_grad():
        torch.onnx.export(
            adapter,
            (dummy,),
            str(out_path),
            input_names=[INPUT_NAME],
            output_names=list(OUTPUT_NAMES),
            dynamic_axes=DYNAMIC_AXES,
            opset_version=opset,
            do_constant_folding=True,
            training=torch.onnx.TrainingMode.EVAL,
            dynamo=False,  # legacy exporter: dynamo path mis-handles dynamic batch
        )

    onnx_model = onnx.load(str(out_path))
    actual_inputs = [i.name for i in onnx_model.graph.input]
    if actual_inputs != [INPUT_NAME]:
        raise OnnxExportError(f"input {actual_inputs} != contract ['{INPUT_NAME}']")
    actual_outputs = [o.name for o in onnx_model.graph.output]
    if set(actual_outputs) != set(OUTPUT_NAMES):
        raise OnnxExportError(
            f"outputs {actual_outputs} != contract {list(OUTPUT_NAMES)}"
        )
    opsets = {op.domain: op.version for op in onnx_model.opset_import}
    if opsets.get("", 0) != OPSET:
        raise OnnxExportError(f"exported opset {opsets.get('')} != {OPSET}")

    # Record provenance metadata (IR_VERSION of the producing onnx package).
    model_name = "aesthetic-prism-hapnet"
    meta = onnx_model.metadata_props.add()
    meta.key = "model"
    meta.value = model_name
    for key, value in (
        ("opset", str(OPSET)),
        ("ir_version", str(onnx.IR_VERSION)),
        ("io_contract", "C-EXPORT-01"),
    ):
        entry = onnx_model.metadata_props.add()
        entry.key = key
        entry.value = value
    onnx.checker.check_model(onnx_model)
    onnx.save(onnx_model, str(out_path))

    return {
        "opset": OPSET,
        "input": INPUT_NAME,
        "outputs": list(OUTPUT_NAMES),
        "ir_version": onnx.IR_VERSION,
        "path": str(out_path),
    }


def _check_provider(providers: Sequence[str]) -> None:
    import onnxruntime  # type: ignore[import-untyped]

    available = set(onnxruntime.get_available_providers())
    for p in providers:
        if p not in available:
            raise OnnxSchemaError(f"provider {p} unavailable; available={sorted(available)}")


def load_session(path: Path, providers: Sequence[str] = ("CPUExecutionProvider",)) -> Any:
    """onnxruntime.InferenceSession + post-load IO contract verification."""
    import onnxruntime  # type: ignore[import-untyped]

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"model file not found: {path}")
    _check_provider(providers)
    sess = onnxruntime.InferenceSession(str(path), providers=list(providers))

    inputs = sess.get_inputs()
    if len(inputs) != 1 or inputs[0].name != INPUT_NAME:
        raise OnnxSchemaError(
            f"input {([i.name for i in inputs])} mismatch: expect '{INPUT_NAME}' (N,3,224,224)"
        )
    shape = tuple(inputs[0].shape)
    if len(shape) != 4 or shape[1:] != (3, 224, 224):
        raise OnnxSchemaError(
            f"input '{inputs[0].name}' shape {shape} mismatch: expect (N,3,224,224)"
        )
    if inputs[0].type != "tensor(float)":
        raise OnnxSchemaError(f"input dtype {inputs[0].type} != tensor(float)")

    outputs = sess.get_outputs()
    if {o.name for o in outputs} != set(OUTPUT_NAMES):
        raise OnnxSchemaError(
            f"outputs {[o.name for o in outputs]} != contract {list(OUTPUT_NAMES)}"
        )
    for o in outputs:
        if o.type != "tensor(float)":
            raise OnnxSchemaError(f"output '{o.name}' dtype {o.type} != tensor(float)")
        oshape = tuple(o.shape)
        if len(oshape) != 2 or oshape[1] != 1:
            raise OnnxSchemaError(f"output '{o.name}' shape {oshape} != (N,1)")

    # E6: in-graph [0,100] domain probe on a zero batch.
    probe = run_session(sess, np.zeros((1, 3, 224, 224), dtype=np.float32))
    for name, value in probe.items():
        vmin, vmax = float(value.min()), float(value.max())
        if vmin < 0.0 or vmax > 100.0:
            raise OnnxSchemaError(
                f"output '{name}' value {vmin if vmin < 0 else vmax} outside [0,100]"
            )
    return sess


def run_session(sess: Any, batch_nchw: np.ndarray) -> dict[str, np.ndarray]:
    """Single-image or batch forward; keys == OUTPUT_NAMES, values (N,1) float32."""
    arr = np.asarray(batch_nchw)
    if arr.dtype != np.float32:
        raise OnnxSchemaError(f"feed dtype {arr.dtype} invalid: expect float32")
    if arr.ndim != 4 or arr.shape[1:] != (3, 224, 224) or arr.shape[0] < 1:
        raise OnnxSchemaError(
            f"feed shape {arr.shape} invalid: expect (N,3,224,224) float32"
        )
    try:
        raw = sess.run(list(OUTPUT_NAMES), {INPUT_NAME: arr})
    except Exception as exc:  # runtime failure surfaced verbatim to the caller
        raise RuntimeError(f"inference failed: {exc}") from exc
    out: dict[str, np.ndarray] = {}
    for name, value in zip(OUTPUT_NAMES, raw, strict=True):
        value = np.asarray(value, dtype=np.float32).reshape(arr.shape[0], 1)
        out[name] = value
    return out
