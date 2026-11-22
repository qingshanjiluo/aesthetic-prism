# C-CONF-01 段5 T-5-02：配置 schema 校验（jsonschema 校验 serve 环境配置）
# 用法：validate_serve_config(dict) -> dict（规范化后配置）；非法抛 ValueError。
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import jsonschema

# serve 配置 schema：AP_* 环境变量规范化后的结构
SERVE_CONFIG_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["mode", "model_path", "device"],
    "properties": {
        "mode": {"enum": ["auto", "mock", "onnx"]},
        "model_path": {"type": "string", "minLength": 1},
        "device": {"enum": ["cpu", "cuda"]},
        "port": {"type": "integer", "minimum": 1, "maximum": 65535},
        "host": {"type": "string", "minLength": 1},
    },
}

# configs/serve/serve.yaml 校验用 schema（若存在该文件）
YAML_CONFIG_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "serve": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "mode": {"enum": ["auto", "mock", "onnx"]},
                "model_path": {"type": "string", "minLength": 1},
                "device": {"enum": ["cpu", "cuda"]},
            },
        }
    },
}


def _env_to_config() -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "mode": os.environ.get("AP_MODE", "auto").strip().lower(),
        "model_path": os.environ.get("AP_MODEL_PATH", "models/hapnet_teacher.onnx"),
        "device": os.environ.get("AP_DEVICE", "cpu").strip().lower(),
    }
    host = os.environ.get("AP_HOST")
    port = os.environ.get("AP_PORT")
    if host:
        cfg["host"] = host
    if port:
        cfg["port"] = int(port)
    return cfg


def validate_serve_config(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """校验 serve 配置（缺省读 AP_* 环境）。非法值抛 ValueError，合法返回规范化 dict。"""
    c = cfg if cfg is not None else _env_to_config()
    try:
        jsonschema.validate(instance=c, schema=SERVE_CONFIG_SCHEMA)
    except jsonschema.ValidationError as exc:
        loc = ".".join(str(p) for p in exc.absolute_path) or "<root>"
        raise ValueError(f"invalid serve config at {loc}: {exc.message}") from None
    return c


def validate_yaml_config(path: str | Path) -> dict[str, Any]:
    """校验 configs/serve/serve.yaml；文件不存在返回空 dict（交由环境变量兜底）。"""
    p = Path(path)
    if not p.is_file():
        return {}
    import yaml

    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    try:
        jsonschema.validate(instance=data, schema=YAML_CONFIG_SCHEMA)
    except jsonschema.ValidationError as exc:
        loc = ".".join(str(p2) for p2 in exc.absolute_path) or "<root>"
        raise ValueError(f"invalid yaml config at {loc}: {exc.message}") from None
    return data


if __name__ == "__main__":  # CLI 自检：python -m aesthetic_prism.serve.config_check
    import json as _json

    print(_json.dumps(validate_serve_config(), ensure_ascii=False))
