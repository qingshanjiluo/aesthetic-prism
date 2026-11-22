"""HAP-Net fusion gate — workorder W-3-01 deliverable 3/8.

C-BRANCH-01 section 3.1 row 9-10 gate math:
  gate_logits = Linear(4*D -> gate_hidden) -> GELU -> Linear(gate_hidden -> 4)
  gate       = softmax(gate_logits, dim=-1) -> (N, 4), each row sums to 1.

The gate consumes the FUSED feature (N, 4*D) per row 9 ('input=fused_feat'),
not the raw branch stack; this matches the ONNX export graph (C-EXPORT-01
section 3.3: Softmax(1) -> (N,4) elementwise-multiply subs -> ReduceSum(1)).

Error semantics E7: row-sum deviation > 1e-4 raises ContractViolationError;
raised from validate_gate_row_sum which HAPNet calls after forward.
"""
from __future__ import annotations

import torch
from torch import nn


class ContractViolationError(RuntimeError):
    """Forward output violates C-BRANCH-01 (missing key / range / gate row-sum).

    args[0] is a human-readable single line '<field>: <reason>'.
    Re-declared here for the fusion layer; model.hapnet re-exports one canonical
    exception object so callers import from a single place.
    """


# Gate row-sum tolerance (C-BRANCH-01 section 3.1 row 10: atol <= 1e-4).
GATE_ROW_SUM_ATOL = 1e-4


def validate_gate_row_sum(gate: torch.Tensor, atol: float = GATE_ROW_SUM_ATOL) -> None:
    """Raise ContractViolationError when any gate row sum deviates > atol.

    Checked in float64 to avoid fp32 summation noise masking a real bug.
    """
    if gate.dim() != 2 or gate.shape[-1] != 4:
        raise ContractViolationError(f"gate: expected shape (N,4), got {tuple(gate.shape)}")
    row_sums = gate.double().sum(dim=-1)
    worst = (row_sums - 1.0).abs().max().item()
    if worst > atol:
        raise ContractViolationError(
            f"gate: row sum {row_sums[0].item():.6f} deviates from 1.0 (atol {atol})"
        )


class FusionGate(nn.Module):
    """FusionGate: fused_feat (N, 4*D) -> gate_logits (N,4) -> softmax -> (N,4).

    forward returns the softmax gate directly (contract section 2.1: return
    (N,4) float32 row-sum=1). Callers wanting logits for diagnostics can read
    gate_logits via the module attribute during training only.
    """

    def __init__(self, fused_dim: int, gate_hidden: int = 128, num_branches: int = 4) -> None:
        super().__init__()
        if fused_dim <= 0 or gate_hidden <= 0:
            raise ValueError(f"gate dims must be > 0, got fused={fused_dim} hidden={gate_hidden}")
        if num_branches != 4:
            raise ValueError(f"num_branches must be 4, got {num_branches}")
        self.num_branches = num_branches
        self.gate_logits = nn.Sequential(
            nn.Linear(fused_dim, gate_hidden),
            nn.GELU(),
            nn.Linear(gate_hidden, num_branches),
        )

    def forward(self, branch_feats: torch.Tensor) -> torch.Tensor:
        """branch_feats may be either (N, 4*D) fused or (N, 4, D) stacked.

        Contract signature names the stacked form; HAPNet passes the fused
        (N, 4*D) vector. Both are accepted: a (N,4,D) tensor is flattened to
        (N, 4*D) first so row order (BRANCH_KEYS) is preserved.
        """
        if branch_feats.dim() == 3:
            branch_feats = branch_feats.flatten(1)
        if branch_feats.dim() != 2:
            raise ContractViolationError(
                f"gate: expected (N,4*D) or (N,4,D), got {tuple(branch_feats.shape)}"
            )
        logits = self.gate_logits(branch_feats)
        return torch.softmax(logits, dim=-1)
