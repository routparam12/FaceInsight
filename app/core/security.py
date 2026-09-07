"""Auth primitives: admin JWTs and hashed device tokens.

Two distinct principals:
  * admin  - HR/portal users, short-lived JWT from username/password.
  * device - kiosk apps, long-lived opaque token, stored only as a hash,
             revocable per device.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings

ALGORITHM = "HS256"


# --- Admin JWT ---------------------------------------------------------------

def create_admin_token(subject: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": "admin",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_admin_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])


def verify_admin_credentials(username: str, password: str) -> bool:
    return hmac.compare_digest(username, settings.admin_username) and hmac.compare_digest(
        password, settings.admin_password
    )


# --- Opaque tokens (device access + provisioning) --------------------------

def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Salted hash bound to JWT_SECRET; tokens are never stored in the clear."""
    return hashlib.sha256(f"{settings.jwt_secret}:{token}".encode()).hexdigest()


def verify_token(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), token_hash)
