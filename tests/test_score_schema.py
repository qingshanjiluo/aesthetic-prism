# r5：POST /score — 六字段 ScoreResponse（C-SERVE-01 §3.2；S1-03 mock 冒烟）
from __future__ import annotations

from typing import Any

import jsonschema

SCORE_KEYS = {"total", "composition", "light", "creativity", "story", "model"}
NUM_KEYS = ("total", "composition", "light", "creativity", "story")

# additionalProperties=false 的显式 schema（黑盒等价 = set 恰等断言，多一键少一键都 FAIL）
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "total": {"type": "number", "minimum": 0, "maximum": 100},
        "composition": {"type": "number", "minimum": 0, "maximum": 100},
        "light": {"type": "number", "minimum": 0, "maximum": 100},
        "creativity": {"type": "number", "minimum": 0, "maximum": 100},
        "story": {"type": "number", "minimum": 0, "maximum": 100},
        "model": {"type": "string", "minLength": 1},
    },
    "required": sorted(SCORE_KEYS),
    "additionalProperties": False,
}


def test_score_six_keys_schema(client, tmp_sample_png) -> None:
    data = tmp_sample_png.read_bytes()
    r = client.post("/score", files={"image": ("sample.png", data, "image/png")})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")
    d = r.json()
    # 六键恰等（additionalProperties=false 黑盒等价）
    assert set(d.keys()) == SCORE_KEYS, sorted(d.keys())
    jsonschema.validate(d, SCHEMA)  # 五分数 0–100 + model 非空 + 无额外键
    for k in NUM_KEYS:
        assert isinstance(d[k], (int, float)) and not isinstance(d[k], bool)
        assert 0 <= d[k] <= 100, (k, d[k])
        # round(x, 1)：最多 1 位小数
        assert round(float(d[k]), 1) == d[k], (k, d[k])
    assert "mock" in str(d["model"]).lower(), d["model"]


def test_score_mock_deterministic(client, tmp_sample_png) -> None:
    """mock 语义：同图恒同分（seed=sha256 前 8 位）。"""
    data = tmp_sample_png.read_bytes()
    r1 = client.post("/score", files={"image": ("sample.png", data, "image/png")})
    r2 = client.post("/score", files={"image": ("sample.png", data, "image/png")})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
