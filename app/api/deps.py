"""Shared FastAPI dependencies: admin (JWT) and device (opaque token) auth."""

from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_admin_token
from app.models.device import Device
from app.services import device_service

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization.split(" ", 1)[1].strip()


async def require_admin(
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    token = _bearer(authorization)
    try:
        claims = decode_admin_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid admin token")
    if claims.get("role") != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")
    return claims


async def require_device(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Device:
    token = _bearer(authorization)
    device = await device_service.authenticate(session, token)
    if device is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "invalid, expired or revoked device token"
        )
    return device


AdminDep = Annotated[dict, Depends(require_admin)]
DeviceDep = Annotated[Device, Depends(require_device)]
