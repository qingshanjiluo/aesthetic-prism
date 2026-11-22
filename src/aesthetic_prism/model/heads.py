"""HAP-Net dual heads + export wrapper — workorder W-3-01 deliverable 4/8.

C-BRANCH-01 section 3.1 rows 7-8, 11-12:
  z_i    = Linear(D -> 1) applied to branch chunk i (i order = BRANCH_KEYS)
  sub    = 100 * sigmoid(z)                -> (N, 4), range [0, 100]
  total  = clamp(sum(gate * sub), 0, 100)  -> (N, 1)
  rank z = Linear(4D -> 128) -> GELU -> Linear(128 -> 1)
  ranking_logit = 100 * tanh(rank z)      -> (N, 1) training-only

Ranking scale note (workorder W-3-01 contract ③): ranking_logit = 100*tanh(...)
keeps the Bradley-Terry score on the 0-100 point scale so tau=10 (03_TRAINING
section 4.1) has meaning; the pre-tanh MLP output stays the contract's
unbounded real head output. ScoreOnlyWrapper strips ranking_logit so the ONNX
graph only ever sees the five SCORE_KEYS (C-EXPORT-01 verdict B).
"""
from __future__ import annotations

import torch
from torch import nn

from .fusion import ContractViolationError

SCORE_KEYS: tuple[str, str, str, str, str] = (
    "total",
    "composition",
    "light",
    "creativity",
    "story",
)


def _check_range(name: str, value: torch.Tensor, lo: float, hi: float) -> None:
    """E8: raise ContractViolationError when any element falls outside [lo, hi].

    detach() first so grad-tracked tensors do not emit a UserWarning per step.
    """
    detached = value.detach()
    vmin = float(detached.min())
    vmax = float(detached.max())
    if vmin < lo or vmax > hi:
        raise ContractViolationError(f"{name}: value {vmin if vmin < lo else vmax} outside [{lo},{hi}]")


class ScoreHead(nn.Module):
    """Score head: per-branch Linear(D->1) logits + gate-weighted total (contract row 7-11).

    forward(fused_feat, gate) with fused_feat (N, 4*D) and gate (N, 4) returns
    (sub (N, 4), total (N, 1)); sub range is enforced, total is clamped in-graph.
    """

    def __init__(self, branch_feat_dim: int, num_branches: int = 4) -> None:
        super().__init__()
        if branch_feat_dim <= 0:
            raise ValueError(f"branch_feat_dim must be > 0, got {branch_feat_dim}")
        if num_branches != 4:
            raise ValueError(f"num_branches must be 4, got {num_branches}")
        self.branch_feat_dim = branch_feat_dim
        self.num_branches = num_branches
        # One Linear per branch chunk; order fixed = BRANCH_KEYS (not stored as
        # state, positional in ModuleList, index i -> BRANCH_KEYS[i]).
        self.branch_linears = nn.ModuleList(
            nn.Linear(branch_feat_dim, 1) for _ in range(num_branches)
        )

    def forward(
        self, fused_feat: torch.Tensor, gate: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        if fused_feat.dim() != 2 or fused_feat.shape[-1] != self.branch_feat_dim * self.num_branches:
            raise ContractViolationError(
                f"fused_feat: expected (N,{self.branch_feat_dim * self.num_branches}), "
                f"got {tuple(fused_feat.shape)}"
            )
        if gate.dim() != 2 or gate.shape[-1] != self.num_branches:
            raise ContractViolationError(
                f"gate: expected (N,{self.num_branches}), got {tuple(gate.shape)}"
            )
        # Split fused (N, 4D) back to branch chunks (N, D); concat order was
        # BRANCH_KEYS so chunk i feeds Linear i (contract row 7 semantics).
        chunks = fused_feat.chunk(self.num_branches, dim=-1)
        z = torch.cat([lin(chunk) for lin, chunk in zip(self.branch_linears, chunks, strict=True)], dim=-1)
        sub = 100.0 * torch.sigmoid(z)
        _check_range("sub", sub, 0.0, 100.0)
        total = (gate * sub).sum(dim=-1, keepdim=True).clamp(0.0, 100.0)
        _check_range("total", total, 0.0, 100.0)
        return sub, total


class RankingHead(nn.Module):
    """Ranking head (Bradley-Terry scorer): training-only, 100*tanh output scale.

    forward(fused_feat) with fused_feat (N, 4*D) returns ranking_logit (N, 1)
    with range (-100, 100) (tanh-bounded); the pre-activation z is unbounded.
    """

    def __init__(self, fused_dim: int, ranking_hidden: int = 128) -> None:
        super().__init__()
        if fused_dim <= 0 or ranking_hidden <= 0:
            raise ValueError(f"ranking dims must be > 0, got fused={fused_dim} hidden={ranking_hidden}")
        self.mlp = nn.Sequential(
            nn.Linear(fused_dim, ranking_hidden),
            nn.GELU(),
            nn.Linear(ranking_hidden, 1),
        )

    def forward(self, fused_feat: torch.Tensor) -> torch.Tensor:
        if fused_feat.dim() != 2:
            raise ContractViolationError(
                f"fused_feat: expected (N,4*D), got {tuple(fused_feat.shape)}"
            )
        return 100.0 * torch.tanh(self.mlp(fused_feat))


class ScoreOnlyWrapper(nn.Module):
    """Export wrapper: eval-mode HAPNet call, strip ranking_logit -> SCORE_KEYS 5-tuple.

    E10: raises ContractViolationError when the wrapped model is still in train()
    mode — callers must .eval() before export (mirrors C-EXPORT-01 E1).
    """

    def __init__(self, model: nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(self, images: torch.Tensor) -> dict[str, torch.Tensor]:
        if self.model.training:
            raise ContractViolationError("wrapper: model must be eval() before export")
        out = self.model(images, return_ranking=False)
        missing = [k for k in SCORE_KEYS if k not in out]
        if missing:
            raise ContractViolationError(f"wrapper: missing score keys {missing}")
        # Rebuild dict in exact SCORE_KEYS order (Python dict insertion order).
        return {k: out[k] for k in SCORE_KEYS}
