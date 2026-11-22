"""aesthetic_prism.model — HAP-Net package (W-3-01).

Public surface follows C-BRANCH-01: HAPNet, ScoreOnlyWrapper, key tuples and
the three exception classes. Import from either aesthetic_prism.model.hapnet
(contract path) or aesthetic_prism.model.model (workorder path).
"""
from __future__ import annotations

from .branches import BRANCH_KEYS
from .fusion import ContractViolationError
from .heads import SCORE_KEYS, ScoreOnlyWrapper
from .model import DICT_KEYS_TRAIN, HAPNet, TensorDtypeError, TensorShapeError, student, teacher

__all__ = [
    "BRANCH_KEYS",
    "DICT_KEYS_TRAIN",
    "SCORE_KEYS",
    "ContractViolationError",
    "HAPNet",
    "ScoreOnlyWrapper",
    "TensorDtypeError",
    "TensorShapeError",
    "student",
    "teacher",
]
