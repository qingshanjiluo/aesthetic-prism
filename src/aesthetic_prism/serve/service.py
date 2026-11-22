# C-SERVE-01 服务层实现（签名不得改动；docs/contracts/score_api_request_response.md §2，含 CW-S1-01）
from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageOps

# ---- 限制常量：服务层唯一事实源，实现与测试共用（契约 §2 常量表，CW-S1-01 加 MAX_INFLIGHT）----
MAX_IMAGE_BYTES: int = 10_485_760
ALLOWED_MIME: set[str] = {"image/jpeg", "image/png"}
SCORE_TIMEOUT_MS: int = 5000
MAX_INFLIGHT: int = 4

SCORE_KEYS: tuple[str, ...] = ("total", "composition", "light", "creativity", "story")
MOCK_MODEL_NAME: str = "mock-deterministic-v1"

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG"
_MIN_SIDE = 16
_MAX_SIDE = 8192


class ApiError(Exception):
    """HTTP 层统一错误。属性: status_code: int; code: str; message: str。"""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class ImageTooLargeError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(413, "payload_too_large", message)


class UnsupportedMediaError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(415, "unsupported_media_type", message)


class InvalidImageError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__(400, "invalid_request", message)


class TooManyRequestsError(ApiError):
    """429 too_many_requests（在途满，W3/CW-S1-01 扩档）。"""

    def __init__(self, message: str = f"inflight limit {MAX_INFLIGHT} reached, retry after 100ms") -> None:
        super().__init__(429, "too_many_requests", message)


class ModelNotReadyError(ApiError):
    def __init__(self, message: str = "model not ready: session unavailable") -> None:
        super().__init__(500, "internal_error", message)


class InferenceError(ApiError):
    def __init__(self, message: str = "inference failed") -> None:
        super().__init__(500, "internal_error", message)


def probe_image(data: bytes, mime: str) -> dict[str, Any]:
    """POST /upload 前置校验：与 score_bytes 同源校验链（大小/空/魔数/解码/尺寸），只返回尺寸元数据不推理。"""
    if len(data) > MAX_IMAGE_BYTES:  # 413
        raise ImageTooLargeError(f"image is {len(data)} bytes, limit {MAX_IMAGE_BYTES}")
    if not data:  # 400 空文件
        raise InvalidImageError("empty image: decoded 0 bytes")
    if mime not in ALLOWED_MIME:  # 415
        raise UnsupportedMediaError(f"mime '{mime}' is not image/jpeg or image/png")
    if not data.startswith((_JPEG_MAGIC, _PNG_MAGIC)):  # 415 魔数不符
        raise UnsupportedMediaError("content is not image/jpeg or image/png")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        raise InvalidImageError(f"image decode failed: {type(exc).__name__}") from None
    transposed = ImageOps.exif_transpose(img)
    ready = transposed if transposed is not None else img
    w, h = ready.size
    if w < _MIN_SIDE or h < _MIN_SIDE:
        raise InvalidImageError(f"image too small: {w}x{h}, min {_MIN_SIDE}x{_MIN_SIDE}")
    if w > _MAX_SIDE or h > _MAX_SIDE:
        raise InvalidImageError(f"image too large: {w}x{h}, max {_MAX_SIDE}x{_MAX_SIDE}")
    return {"width": w, "height": h, "bytes": len(data), "mime": mime}


class ScoreService:
    """mock / onnx 两模式（切换语义见 docs/05_DEPLOY §1.3）：
    AP_MODE=mock|onnx 显式优先；auto 按 model_path 文件存在与否自动选，缺失走 mock 记 warn。"""

    def __init__(self, model_path: Path, device: Literal["cpu", "cuda"] = "cpu") -> None:
        import os

        if device not in ("cpu", "cuda"):
            raise ValueError(f"device must be 'cpu' or 'cuda', got {device!r}")
        self.model_path = Path(model_path)
        self.device: str = device
        mode = os.environ.get("AP_MODE", "auto").strip().lower()
        if mode not in ("auto", "mock", "onnx"):
            raise ValueError(f"AP_MODE must be auto|mock|onnx, got {mode!r}")
        if mode == "onnx":
            if not self.model_path.is_file():
                raise ModelNotReadyError(f"model not ready: file not found: {self.model_path.name}")
            self.mode = "onnx"
        elif mode == "mock":
            self.mode = "mock"
        else:  # auto：有模型 onnx，无模型 mock（段1 默认可跑）
            self.mode = "onnx" if self.model_path.is_file() else "mock"
        self._session: Any | None = None
        if self.mode == "onnx":
            self._load_session()
        self.mock_model_name = MOCK_MODEL_NAME

    def _load_session(self) -> None:
        try:
            import onnxruntime as ort  # type: ignore[import-untyped]

            providers = [f"{self.device}ExecutionProvider", "CPUExecutionProvider"]
            self._session = ort.InferenceSession(str(self.model_path), providers=providers)
        except Exception as exc:
            self._session = None
            import logging

            logging.getLogger("aesthetic_prism.serve").warning("session load failed: %s", type(exc).__name__)

    @property
    def ready(self) -> bool:
        return self.mode == "mock" or self._session is not None

    @property
    def model_name(self) -> str | None:
        if self.mode == "mock":
            return self.mock_model_name
        if self._session is None:
            return None
        meta = getattr(self._session, "modelmeta", None)
        return str(meta.graph_name or "hapnet-teacher-v1") if meta else "hapnet-teacher-v1"

    def score_bytes(self, data: bytes, mime: str) -> dict[str, float]:
        """返回键恰为 total/composition/light/creativity/story 的 dict，值 0–100。"""
        if len(data) > MAX_IMAGE_BYTES:  # E4 → 413
            raise ImageTooLargeError(f"image is {len(data)} bytes, limit {MAX_IMAGE_BYTES}")
        if not data:  # E10 空文件（解码 0 字节）→ 400
            raise InvalidImageError("empty image: decoded 0 bytes")
        if mime not in ALLOWED_MIME:  # E2 → 415
            raise UnsupportedMediaError(f"mime '{mime}' is not image/jpeg or image/png")
        if not data.startswith((_JPEG_MAGIC, _PNG_MAGIC)):  # 魔数不符 → 415
            raise UnsupportedMediaError("content is not image/jpeg or image/png")
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception as exc:
            raise InvalidImageError(f"image decode failed: {type(exc).__name__}") from None
        transposed = ImageOps.exif_transpose(img)
        img_ready = transposed if transposed is not None else img
        w, h = img_ready.size
        if w < _MIN_SIDE or h < _MIN_SIDE:  # E5 → 400
            raise InvalidImageError(f"image too small: {w}x{h}, min {_MIN_SIDE}x{_MIN_SIDE}")
        if w > _MAX_SIDE or h > _MAX_SIDE:
            raise InvalidImageError(f"image too large: {w}x{h}, max {_MAX_SIDE}x{_MAX_SIDE}")
        if self.mode == "mock":
            return self._mock_scores(data)
        if self._session is None:  # E6 → 500
            raise ModelNotReadyError("model not ready: session unavailable")
        return self._onnx_scores(img_ready)

    def _mock_scores(self, data: bytes) -> dict[str, float]:
        """mock：seed = sha256 前 8 位，同图恒同分，round 1 位（0–100）。"""
        import random

        rng = random.Random(int(hashlib.sha256(data).hexdigest()[:8], 16))
        return {k: round(rng.random() * 100.0, 1) for k in SCORE_KEYS}

    def _onnx_scores(self, img: Image.Image) -> dict[str, float]:
        """预/后处理对齐 C-EXPORT-01 §3 与 C-SERVE-01 §1、§3.2。"""
        import numpy as np

        try:
            resized = img.convert("RGB").resize((224, 224), Image.Resampling.BILINEAR)
            arr = np.asarray(resized, dtype=np.float32) / 255.0
            mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
            std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
            x = ((arr - mean) / std).transpose(2, 0, 1)[None, ...]
            sess = self._session
            if sess is None:
                raise ModelNotReadyError("model not ready: session unavailable")
            outputs = sess.run(None, {"images": x})
            names = [o.name for o in sess.get_outputs()]
            flat = dict(zip(names, outputs, strict=True))
            return {k: round(float(np.clip(flat[k].reshape(-1)[0], 0.0, 100.0)), 1) for k in SCORE_KEYS}
        except ApiError:
            raise
        except Exception as exc:
            raise InferenceError(f"inference failed: {type(exc).__name__}") from None
