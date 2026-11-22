"""Data subpackage: C-DATA-01 dataset sample schema (contract-frozen API)."""
from .dataset import AestheticDataset, assert_no_leakage
from .schema import (
    DatasetValidationError,
    iter_dataset_jsonl,
    load_dataset_sample,
    split_of,
    validate_dataset_sample,
)

__all__ = [
    "AestheticDataset",
    "DatasetValidationError",
    "assert_no_leakage",
    "iter_dataset_jsonl",
    "load_dataset_sample",
    "split_of",
    "validate_dataset_sample",
]
