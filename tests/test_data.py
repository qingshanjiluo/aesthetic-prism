# tests/test_data.py: segment-2 data gates (S3-01 shape, S2-04 decode, split leakage,
# Plan-B bad-line semantics per C-DATA-01 section 4 E9 / section 5.5).
from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch
from PIL import Image

from aesthetic_prism.data import (
    AestheticDataset,
    DatasetValidationError,
    assert_no_leakage,
    iter_dataset_jsonl,
    load_dataset_sample,
    split_of,
    validate_dataset_sample,
)

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "synthetic" / "index.json"


def _samples() -> list[dict]:
    return json.loads(INDEX.read_text(encoding="utf-8"))["samples"]


def test_dataloader_shape() -> None:
    """S3-01: dataloader shape contract (node id test_dataloader_shape per 00_PRD AC1/07_PLAN/08)."""
    ds = AestheticDataset(INDEX, split="train")
    x, y = ds[0]["image"], ds[0]["labels"]
    assert x.shape == (3, 224, 224) and x.dtype == torch.float32
    assert y.shape == (4,) and bool((y >= 0).all()) and bool((y <= 100).all())
    loader = torch.utils.data.DataLoader(ds, batch_size=4)
    batch = next(iter(loader))
    bx, by = batch["image"], batch["labels"]
    assert bx.shape == (4, 3, 224, 224) and by.shape == (4, 4)
    # ImageNet norm extrema: (0-0.485)/0.229=-2.1179039, (1-0.406)/0.225=2.6400000000000004 (float ulp); keep 1-ulp margin
    assert float(bx.min()) >= -2.118 and float(bx.max()) <= 2.6401


def test_schema_full_validate() -> None:
    samples = _samples()
    assert len(samples) >= 200, len(samples)
    for s in samples:
        validate_dataset_sample(s)


def test_all_decode() -> None:
    bad = []
    for s in _samples():
        try:
            Image.open(ROOT / s["image_path"]).verify()
        except Exception:
            bad.append(s["image_path"])
    assert bad == []


def test_split_no_leakage() -> None:
    samples = _samples()
    sets = {sp: {s["id"] for s in samples if split_of(s["id"]) == sp} for sp in ("train", "val", "test")}
    assert all(sets[a] & sets[b] == set() for a in sets for b in sets if a < b)
    sha_split: dict[str, str] = {}
    for s in samples:
        prev = sha_split.setdefault(s["image_sha256"], split_of(s["id"]))
        assert prev == split_of(s["id"]), (s["id"], prev)
    assert_no_leakage(samples)  # must not raise


GOOD = json.dumps({
    "id": "syn_000001", "image_path": "data/synthetic/syn_000001.png",
    "image_sha256": "0d68a002600799244210f3fee9d34a1dfc4fa23f6b06beda4a42dfded542980c",
    "bytes": 666, "width": 256, "height": 256, "source": "synthetic",
    "labels": {"total": 50.0, "composition": 50.0, "light": 50.0, "creativity": 50.0, "story": 50.0},
})


def test_badline_semantics(tmp_path: Path) -> None:
    # (a) 3 physical lines, 2nd broken -> skip + callback line_no=2 (1-based)
    p1 = tmp_path / "a.jsonl"
    p1.write_text(GOOD + "\n{broken json\n" + GOOD + "\n", encoding="utf-8")
    seen, bad = [], []
    for s in iter_dataset_jsonl(p1, on_bad_line=bad.append):
        seen.append(s["id"])
    assert len(seen) == 2 and bad == [{"line_no": 2, "error": "invalid json"}]
    # (b) blank line counts physically: valid / blank / broken / valid -> line_no=3
    p2 = tmp_path / "b.jsonl"
    p2.write_text(GOOD + "\n\n{broken json\n" + GOOD + "\n", encoding="utf-8")
    seen2, bad2 = [], []
    for s in iter_dataset_jsonl(p2, on_bad_line=bad2.append):
        seen2.append(s["id"])
    assert len(seen2) == 2 and bad2 == [{"line_no": 3, "error": "invalid json"}]
    # (c) single-file entry stays strict (Plan-B keeps load_dataset_sample strict)
    with pytest.raises(DatasetValidationError, match="body: invalid json"):
        load_dataset_sample(p1)
