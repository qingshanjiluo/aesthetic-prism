"""Torch Dataset for DatasetSample JSONL / index.json (W-2-02 s4).

Preprocess is frozen by docs/01_ARCH.md section 2 and C-EXPORT-01 section 3.1:
RGB -> bilinear resize 224x224 -> x=(px/255-mean)/std,
mean=(0.485,0.456,0.406), std=(0.229,0.224,0.225), value range [-2.1179, 2.6400].
Reading goes through data.schema.iter_dataset_jsonl (Plan-B bad-line skip),
except index.json which exposes a 'samples' array; both share one loader below.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal

import numpy as np
import torch
from PIL import Image

from .schema import split_of, validate_dataset_sample

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)
BRANCH_KEYS = ("composition", "light", "creativity", "story")  # contract order


def _load_samples(path: Path) -> Iterator[dict[str, Any]]:
    """Yield validated samples from index.json ('samples' array) or .jsonl file."""
    if path.suffix == ".jsonl":
        from .schema import iter_dataset_jsonl

        yield from iter_dataset_jsonl(path)
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    for sample in data["samples"] if isinstance(data, dict) else data:
        validate_dataset_sample(sample)
        yield sample


def _preprocess(img_path: Path, image_size: int) -> torch.Tensor:
    """RGB -> resize (bilinear, square canvas) -> ImageNet normalize -> (3,S,S) float32."""
    img = Image.open(img_path).convert("RGB")
    img = img.resize((image_size, image_size), Image.Resampling.BILINEAR)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr2: np.ndarray = (
        arr - np.asarray(MEAN, dtype=np.float32)
    ) / np.asarray(STD, dtype=np.float32)
    return torch.from_numpy(
        np.ascontiguousarray(arr2.transpose(2, 0, 1).astype(np.float32))
    )


class AestheticDataset(torch.utils.data.Dataset):
    """DatasetSample reader with split_of-based filtering (C-DATA-01 2.2)."""

    def __init__(
        self,
        source: str | Path,
        *,
        split: Literal["train", "val", "test"] | None = None,
        image_size: int = 224,
        root: str | Path | None = None,
    ) -> None:
        self.image_size = image_size
        self.root = Path(root) if root is not None else Path(__file__).resolve().parents[3]
        self.split = split
        self.samples = [
            s for s in _load_samples(Path(source)) if split is None or split_of(s["id"]) == split
        ]

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        s = self.samples[idx]
        img = _preprocess(self.root / s["image_path"], self.image_size)
        labels = torch.tensor([s["labels"][k] for k in BRANCH_KEYS], dtype=torch.float32)
        return {
            "image": img,
            "labels": labels,
            "total": torch.tensor(s["labels"]["total"], dtype=torch.float32),
            "id": s["id"],
        }


def assert_no_leakage(samples: list[dict[str, Any]]) -> None:
    """Same image_sha256 must live in exactly one split; raise AssertionError otherwise."""
    by_split: dict[str, dict[str, str]] = {}
    for s in samples:
        sp = split_of(s["id"])
        owner = by_split.setdefault(sp, {})
        sha = s["image_sha256"]
        if sha in owner:
            continue
        owner[sha] = s["id"]
        for other, mapping in by_split.items():
            if other != sp and sha in mapping:
                raise AssertionError(
                    f"leakage: image_sha256 {sha} in {other} as {mapping[sha]} and in {sp} as {s['id']}"
                )
