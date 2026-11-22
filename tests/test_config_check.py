"""C-CONF-01 / T-5-02: config_check schema validation tests."""
from __future__ import annotations

import pytest

from aesthetic_prism.serve.config_check import (
    validate_serve_config,
    validate_yaml_config,
)


def test_valid_minimal_config() -> None:
    cfg = validate_serve_config({"mode": "onnx", "model_path": "artifacts/student.onnx", "device": "cpu"})
    assert cfg["mode"] == "onnx"
    assert cfg["device"] == "cpu"


def test_valid_full_config_with_host_port() -> None:
    cfg = validate_serve_config({
        "mode": "mock",
        "model_path": "m.onnx",
        "device": "cuda",
        "host": "0.0.0.0",
        "port": 8000,
    })
    assert cfg["port"] == 8000 and cfg["host"] == "0.0.0.0"


def test_invalid_mode_rejected() -> None:
    with pytest.raises(ValueError, match="mode"):
        validate_serve_config({"mode": "bogus", "model_path": "m.onnx", "device": "cpu"})


def test_invalid_port_range_rejected() -> None:
    with pytest.raises(ValueError, match="port"):
        validate_serve_config({"mode": "mock", "model_path": "m.onnx", "device": "cpu", "port": 0})


def test_unknown_key_rejected() -> None:
    with pytest.raises(ValueError):
        validate_serve_config({"mode": "mock", "model_path": "m.onnx", "device": "cpu", "zzz": 1})


def test_missing_required_rejected() -> None:
    with pytest.raises(ValueError):
        validate_serve_config({"mode": "mock"})


def test_env_defaults() -> None:
    cfg = validate_serve_config(None)  # 从 AP_* 环境读（未设置时取默认值）
    assert cfg["mode"] in ("auto", "mock", "onnx")
    assert cfg["device"] in ("cpu", "cuda")


def test_yaml_missing_file_returns_empty(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert validate_yaml_config(tmp_path / "nope.yaml") == {}


def test_yaml_valid(tmp_path) -> None:  # type: ignore[no-untyped-def]
    f = tmp_path / "serve.yaml"
    f.write_text("serve:\n  mode: onnx\n  device: cpu\n", encoding="utf-8")
    data = validate_yaml_config(f)
    assert data["serve"]["mode"] == "onnx"


def test_yaml_invalid(tmp_path) -> None:  # type: ignore[no-untyped-def]
    f = tmp_path / "serve.yaml"
    f.write_text("serve:\n  mode: bogus\n", encoding="utf-8")
    with pytest.raises(ValueError, match="yaml"):
        validate_yaml_config(f)
