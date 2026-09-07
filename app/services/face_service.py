"""Embedding math and the enrollment-time encoder.

The device sends its own embedding for attendance, so the server never needs an
encoder on that path. The encoder here exists only to turn enrollment *images*
into templates (and to re-embed them on a model upgrade).
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Protocol

import numpy as np

from app.core.config import settings


def to_vector(values: list[float]) -> np.ndarray:
    v = np.asarray(values, dtype=np.float32)
    if v.ndim != 1:
        raise ValueError("embedding must be 1-D")
    return v


def l2_normalize(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n == 0.0:
        raise ValueError("zero-norm embedding")
    return v / n


def validate_dim(v: np.ndarray) -> np.ndarray:
    if v.shape[0] != settings.embedding_dim:
        raise ValueError(
            f"embedding dim {v.shape[0]} != expected {settings.embedding_dim}"
        )
    return v


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Both inputs assumed L2-normalised."""
    return float(np.dot(a, b))


def max_cosine(probe: np.ndarray, templates: list[list[float]]) -> float:
    best = -1.0
    for t in templates:
        best = max(best, cosine(probe, to_vector(t)))
    return best


# --- Encoder ---------------------------------------------------------------

class Encoder(Protocol):
    model_version: str

    def embed(self, image_bytes: bytes) -> np.ndarray: ...


class StubEncoder:
    """Deterministic pseudo-embedding derived from the image bytes. Lets the
    full enrollment -> gallery -> attendance path run in dev/CI without ONNX.
    Same bytes -> same vector, so tests are stable; not a real face model."""

    def __init__(self, model_version: str, dim: int):
        self.model_version = model_version
        self._dim = dim

    def embed(self, image_bytes: bytes) -> np.ndarray:
        seed = int.from_bytes(hashlib.sha256(image_bytes).digest()[:8], "big")
        rng = np.random.default_rng(seed)
        return l2_normalize(rng.standard_normal(self._dim).astype(np.float32))


class OnnxArcFaceEncoder:
    def __init__(self, model_path: str, model_version: str, dim: int):
        import onnxruntime as ort  # lazy: optional dependency

        self.model_version = model_version
        self._dim = dim
        self._session = ort.InferenceSession(
            model_path, providers=["CPUExecutionProvider"]
        )
        self._input_name = self._session.get_inputs()[0].name

    def _preprocess(self, image_bytes: bytes) -> np.ndarray:
        # NOTE: must match the Android client's preprocessing exactly
        # (112x112 RGB, aligned, (x-127.5)/128). Wiring a real decoder/aligner
        # is deployment-specific and intentionally left as a single seam here.
        raise NotImplementedError(
            "Wire face detection + alignment to match the client pipeline"
        )

    def embed(self, image_bytes: bytes) -> np.ndarray:
        blob = self._preprocess(image_bytes)
        out = self._session.run(None, {self._input_name: blob})[0][0]
        return l2_normalize(np.asarray(out, dtype=np.float32))


@lru_cache
def get_encoder() -> Encoder:
    if settings.face_model_path:
        return OnnxArcFaceEncoder(
            settings.face_model_path, settings.model_version, settings.embedding_dim
        )
    return StubEncoder(settings.model_version, settings.embedding_dim)
