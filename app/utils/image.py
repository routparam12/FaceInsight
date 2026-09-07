import hashlib
import os
from pathlib import Path

from app.core.config import settings

_ALLOWED = {"image/jpeg", "image/png", "image/webp"}


def _fernet():
    key = settings.enrollment_encryption_key.strip()
    if not key:
        return None
    from cryptography.fernet import Fernet

    return Fernet(key.encode())


def validate_content_type(content_type: str | None) -> str:
    if content_type not in _ALLOWED:
        raise ValueError(f"unsupported content_type: {content_type!r}")
    return content_type


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def storage_root() -> Path:
    root = Path(settings.storage_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_bytes(key: str, data: bytes) -> bool:
    """Persist enrollment image bytes. Returns whether they were encrypted."""
    f = _fernet()
    encrypted = f is not None
    payload = f.encrypt(data) if f else data
    path = storage_root() / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return encrypted


def load_bytes(key: str, encrypted: bool) -> bytes:
    payload = (storage_root() / key).read_bytes()
    if not encrypted:
        return payload
    f = _fernet()
    if f is None:
        raise RuntimeError("ENROLLMENT_ENCRYPTION_KEY not set; cannot decrypt image")
    return f.decrypt(payload)


def delete_bytes(key: str) -> None:
    try:
        os.remove(storage_root() / key)
    except FileNotFoundError:
        pass
