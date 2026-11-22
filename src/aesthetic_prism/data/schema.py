"""C-DATA-01 dataset sample schema (contract-frozen signatures, do not alter)."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Literal

_ID_RE = re.compile(r"^(syn|img)_[0-9]{6}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_PATH_RE = re.compile(r"^[^\\]*\.(jpg|jpeg|png)$")
_KEYS = ("total", "composition", "light", "creativity", "story")
logger = logging.getLogger(__name__)


class DatasetValidationError(ValueError):
    """DatasetSample validation failure. args[0] is '<field>: <reason>'."""


def _err(field: str, reason: str) -> DatasetValidationError:
    return DatasetValidationError(f"{field}: {reason}")


def _check_labels(labels: Any) -> None:
    if not isinstance(labels, dict):
        raise _err("labels", "expected object or null")
    if not all(k in labels for k in _KEYS):
        missing = next(k for k in _KEYS if k not in labels)
        raise _err(f"labels.{missing}", "required when labels != null")
    extra = set(labels) - set(_KEYS) - {"rater_count"}
    if extra:
        raise _err(f"labels.{min(extra)}", "unexpected field")
    for k in _KEYS:
        v = labels[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise _err(f"labels.{k}", f"{v!r} is not a number")
        if not 0 <= v <= 100:
            raise _err(
                f"labels.{k}",
                f"{v} is {'greater than maximum 100' if v > 100 else 'less than minimum 0'}",
            )
    if "rater_count" in labels:
        rc = labels["rater_count"]
        if isinstance(rc, bool) or not isinstance(rc, int) or not 1 <= rc <= 100:
            raise _err("labels.rater_count", f"{rc!r} not in 1..100")


def validate_dataset_sample(sample: dict[str, Any]) -> None:
    """Validate against contract C-DATA-01 section 3.3 schema + rules R1/R2."""
    if not isinstance(sample, dict):
        raise _err("root", "expected object")
    required = (
        "id", "image_path", "image_sha256", "bytes", "width", "height", "source", "labels",
    )
    for k in required:
        if k not in sample:
            raise _err(k, "required")
    extra = set(sample) - set(required)
    if extra:
        raise _err(min(extra), "unexpected field")
    sid = sample["id"]
    if not isinstance(sid, str) or not _ID_RE.match(sid):
        raise _err("id", "pattern '^(syn|img)_[0-9]{6}$' failed")
    p = sample["image_path"]
    if not isinstance(p, str) or len(p) > 260 or not _PATH_RE.match(p):
        raise _err("image_path", "must be a .jpg/.jpeg/.png posix path of len<=260")
    if not isinstance(sample["image_sha256"], str) or not _SHA_RE.match(sample["image_sha256"]):
        raise _err("image_sha256", "must match ^[0-9a-f]{64}$")
    for k, lo, hi in (("bytes", 1, 10_000_000), ("width", 16, 8192), ("height", 16, 8192)):
        v = sample[k]
        if isinstance(v, bool) or not isinstance(v, int):
            raise _err(k, f"{v!r} is not an integer")
        if v < lo:
            raise _err(k, f"{v} is less than minimum {lo}")
        if v > hi:
            raise _err(k, f"{v} is greater than maximum {hi}")
    if sample["source"] not in ("synthetic", "labeled"):
        raise _err("source", f"{sample['source']!r} not in ['synthetic', 'labeled']")
    labels = sample["labels"]
    if sample["source"] == "labeled":
        if labels is None:
            raise _err("labels", "required for source=labeled")
        if "rater_count" not in labels:
            raise _err("labels.rater_count", "required for source=labeled")
    if labels is not None:
        _check_labels(labels)


def load_dataset_sample(path: str | Path) -> dict[str, Any]:
    """Strict single-file load; raises FileNotFoundError or DatasetValidationError."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        sample = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _err("body", "invalid json") from exc
    validate_dataset_sample(sample)
    return sample


def iter_dataset_jsonl(
    path: str | Path,
    *,
    on_bad_line: Callable[[dict[str, Any]], None] | None = None,
) -> Iterator[dict[str, Any]]:
    """Plan-B skip semantics (C-DATA-01 section 4 E9): bad lines are skipped with a
    structured warning ('bad_line: {"line_no": N, "error": ...}', 1-based physical
    line number, blank lines count silently) and reported via on_bad_line."""
    with Path(path).open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                sample = json.loads(line)
                validate_dataset_sample(sample)
            except (json.JSONDecodeError, DatasetValidationError) as exc:
                reason = "invalid json" if isinstance(exc, json.JSONDecodeError) else str(exc)
                info = {"line_no": line_no, "error": reason}
                logger.warning('bad_line: {"line_no": %d, "error": "%s"}', line_no, reason)
                if on_bad_line is not None:
                    on_bad_line(info)
                continue
            yield sample


def split_of(sample_id: str) -> Literal["train", "val", "test"]:
    """Deterministic 80/10/10 split (C-DATA-01 section 2.2, sha256 first-8-hex)."""
    if not isinstance(sample_id, str) or not _ID_RE.match(sample_id):
        raise _err("id", "pattern '^(syn|img)_[0-9]{6}$' failed")
    v = int(hashlib.sha256(sample_id.encode("utf-8")).hexdigest()[:8], 16) % 20
    return "train" if v < 16 else ("val" if v < 18 else "test")
