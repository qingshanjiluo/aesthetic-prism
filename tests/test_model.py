"""Segment-3 gate tests — workorder W-3-01 deliverable 6/8.

Node ids are verbatim per workorder contract item ⑤ (pre-seeded to prevent
S3-01 drift-replication); QA runs them through 08_ACCEPTANCE verbatim commands:
  python -m pytest -q tests/test_model.py::test_forward_backward_shapes   (S3-02)
  python -m pytest -q tests/test_model.py::test_checkpoint_roundtrip       (S3-04)
  python -m pytest -q tests/test_model.py::test_output_range               (S3-05)

Assertions follow 08_ACCEPTANCE text:
  S3-02: output (B,4) batch view; four branch grads non-None and finite.
  S3-04: save->load state_dict key sets equal; parameter values equal atol=0.
         Bundle layout follows docs/03_TRAINING.md section 8 (schema_version /
         stage / step / model / optimizer / rng / config / val_metrics).
  S3-05: 100 random batches; all score outputs within [0,100] (post sigmoid/clamp).

Fixtures are synthetic (torch.randn) — no sample values are frozen into
assertions (DATA is regenerating data/ in parallel; per workorder the smoke
self-check may use tmp fixtures, assertions must stay data-independent).
"""
from __future__ import annotations

import sys
from pathlib import Path

import torch

# sys.path injection mirrors tests/conftest.py so bare `pytest` also works.
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from aesthetic_prism.model import (
    BRANCH_KEYS,
    DICT_KEYS_TRAIN,
    SCORE_KEYS,
    ContractViolationError,
    HAPNet,
    ScoreOnlyWrapper,
)

SCORE_ONLY_KEYS = SCORE_KEYS
B = 2  # batch size used by the forward/backward shape gate


def _new_model() -> HAPNet:
    """Deterministic init so gates are reproducible across runs."""
    torch.manual_seed(42)
    return HAPNet()


def test_forward_backward_shapes() -> None:
    """S3-02: forward shapes + four-branch grads (non-None, finite)."""
    model = _new_model()
    model.train()
    x = torch.randn(B, 3, 224, 224)
    assert x.shape == (B, 3, 224, 224)  # input contract row 1

    out = model(x)
    # Train dict key set and order (contract section 3.2).
    assert list(out.keys()) == list(DICT_KEYS_TRAIN)
    # Per-key shapes: five score keys (N,1); batch view (B,4) per AC2 semantics.
    for key in SCORE_KEYS:
        assert out[key].shape == (B, 1), f"{key} {tuple(out[key].shape)}"
    batch_view = torch.cat([out[k] for k in BRANCH_KEYS], dim=-1)
    assert batch_view.shape == (B, 4)  # AC2 (B,4) batch view
    assert out["ranking_logit"].shape == (B, 1)

    # Backward through every head input so all four branch towers receive grad.
    loss = batch_view.sum() + out["total"].sum() + out["ranking_logit"].sum()
    loss.backward()

    # S3-02 literal: four branch gradients non-None and finite.
    for idx, branch in enumerate(model.branches.branches):
        grads = [p.grad for p in branch.parameters()]
        assert all(g is not None for g in grads), f"branch {idx} ({BRANCH_KEYS[idx]}) has None grad"
        assert all(torch.isfinite(g).all() for g in grads), f"branch {idx} grad not finite"
    # Backbone (stem/trunk) must also train end-to-end.
    for name, param in model.stem.named_parameters():
        assert param.grad is not None, f"stem.{name} grad None"
        assert torch.isfinite(param.grad).all(), f"stem.{name} grad not finite"
    for name, param in model.trunk.named_parameters():
        assert param.grad is not None, f"trunk.{name} grad None"
        assert torch.isfinite(param.grad).all(), f"trunk.{name} grad not finite"


def test_checkpoint_roundtrip(tmp_path: Path) -> None:
    """S3-04: save->load state_dict keys equal, values equal atol=0 (03 §8)."""
    torch.manual_seed(42)
    model = HAPNet()
    model.eval()

    # Optimizer exists so the bundle mirrors 03_TRAINING section 8.1 layout.
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    bundle = {
        "schema_version": 1,
        "stage": 2,
        "step": 7,
        "model": {k: v.detach().cpu() for k, v in model.state_dict().items()},
        "optimizer": optimizer.state_dict(),
        "rng": {"python": 0, "numpy": 0, "torch": torch.random.get_rng_state()},
        "config": {"stage": 2, "steps": 5000, "lr": 3e-4, "alpha": 0.3, "seed": 42},
        "val_metrics": {},
    }
    ckpt = tmp_path / "roundtrip.pt"
    torch.save(bundle, ckpt)

    restored = torch.load(ckpt, map_location="cpu", weights_only=False)
    fresh = HAPNet()
    # strict=True: key-set equality is enforced by load itself (E14/T4).
    fresh.load_state_dict(restored["model"], strict=True)

    original_keys = set(model.state_dict().keys())
    restored_keys = set(restored["model"].keys())
    fresh_keys = set(fresh.state_dict().keys())
    assert original_keys == restored_keys == fresh_keys

    # Value equality atol=0 (torch.equal: bit-exact, stricter than allclose).
    a, b = model.state_dict(), fresh.state_dict()
    for key in sorted(original_keys):
        assert torch.equal(a[key], b[key]), f"{key} value mismatch after roundtrip"

    # Bundle schema fields present (03_TRAINING section 8.1).
    for field in ("schema_version", "stage", "step", "model", "optimizer", "rng", "config", "val_metrics"):
        assert field in restored, f"bundle missing {field}"

    # Fresh model must be eval-inferable after restore (no NaN, five keys).
    out = fresh.eval()(torch.randn(1, 3, 224, 224))
    assert list(out.keys()) == list(DICT_KEYS_TRAIN)
    assert all(torch.isfinite(v).all() for v in out.values())


def test_output_range() -> None:
    """S3-05: 100 random batches; every score output in [0,100] (post sigmoid/clamp)."""
    torch.manual_seed(42)
    model = HAPNet().eval()  # eval mode: BN running stats, deterministic
    with torch.no_grad():
        for i in range(100):
            x = torch.randn(1, 3, 224, 224)
            out = model(x, return_ranking=False)
            assert list(out.keys()) == list(SCORE_ONLY_KEYS)
            for key in SCORE_ONLY_KEYS:
                value = out[key]
                lo, hi = float(value.min()), float(value.max())
                assert lo >= 0.0 and hi <= 100.0, f"batch {i} {key}={lo}..{hi} outside [0,100]"
            # ranking_logit excluded (unbounded pre-tanh scale); train dict still consistent.
            train_out = model(x)
            assert torch.isfinite(train_out["ranking_logit"]).all()


def test_error_semantics_e1_to_e11() -> None:
    """Contract section 4 spot-check: E1-E6 + E11 raise with exact messages."""
    from aesthetic_prism.model import TensorDtypeError, TensorShapeError

    model = HAPNet().eval()
    x = torch.randn(1, 3, 224, 224)

    cases = [
        (TensorShapeError, lambda: model(torch.randn(3, 224, 224)), "rank 4"),
        (TensorShapeError, lambda: model(torch.randn(1, 1, 224, 224)), "3 channels"),
        (TensorShapeError, lambda: model(torch.randn(1, 3, 512, 512)), "224x224"),
        (TensorDtypeError, lambda: model(x.half()), "float32"),
        (TensorShapeError, lambda: model(torch.randn(0, 3, 224, 224)), "batch dim must be >= 1"),
        (ValueError, lambda: HAPNet(num_branches=3), "num_branches must be 4"),
        (ValueError, lambda: HAPNet(stem_channels=0), "stem_channels must be > 0"),
    ]
    for exc, fn, needle in cases:
        try:
            fn()
        except exc as err:
            assert needle in str(err), f"message {err} lacks {needle}"
        else:
            raise AssertionError(f"expected {exc.__name__} for {needle}")

    xbad = torch.randn(1, 3, 224, 224)
    xbad[0, 0, 57, 3] = float("nan")
    try:
        model(xbad)
    except ContractViolationError as err:
        assert "NaN/Inf" in str(err)
    else:
        raise AssertionError("E11 NaN input did not raise ContractViolationError")


def test_score_only_wrapper_strips_ranking() -> None:
    """Verdict B: wrapper output key set = SCORE_KEYS, order preserved; E10 train mode."""
    model = HAPNet().eval()
    wrapper = ScoreOnlyWrapper(model)
    out = wrapper(torch.randn(1, 3, 224, 224))
    assert list(out.keys()) == list(SCORE_KEYS)
    assert "ranking_logit" not in out

    model.train()  # E10: wrapper must refuse train-mode model
    try:
        wrapper(torch.randn(1, 3, 224, 224))
    except ContractViolationError as err:
        assert "eval()" in str(err)
    else:
        raise AssertionError("E10 train-mode wrapper call did not raise")
