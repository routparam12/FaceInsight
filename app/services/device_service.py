"""Device lifecycle: create -> activate (exchange provisioning token) ->
authenticate per request -> revoke."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import generate_token, hash_token
from app.models.device import Device
from app.utils.time import as_utc, utcnow


@dataclass
class CreatedDevice:
    device: Device
    provisioning_token: str  # shown once


@dataclass
class ActivatedDevice:
    device: Device
    access_token: str  # shown once
    expires_in: int


async def create_device(session: AsyncSession, name: str, site_id: str) -> CreatedDevice:
    provisioning_token = generate_token()
    device = Device(
        name=name,
        site_id=site_id,
        status="active",
        provisioning_token_hash=hash_token(provisioning_token),
    )
    session.add(device)
    await session.commit()
    await session.refresh(device)
    return CreatedDevice(device=device, provisioning_token=provisioning_token)


async def activate_device(
    session: AsyncSession, provisioning_token: str
) -> ActivatedDevice | None:
    device = await session.scalar(
        select(Device).where(
            Device.provisioning_token_hash == hash_token(provisioning_token)
        )
    )
    if device is None or device.status != "active":
        return None

    access_token = generate_token()
    now = utcnow()
    device.access_token_hash = hash_token(access_token)
    device.token_expires_at = now + timedelta(days=settings.device_token_ttl_days)
    device.provisioning_token_hash = None  # single use
    device.provisioned_at = now
    device.last_seen_at = now
    await session.commit()
    await session.refresh(device)
    return ActivatedDevice(
        device=device,
        access_token=access_token,
        expires_in=settings.device_token_ttl_days * 86400,
    )


async def authenticate(session: AsyncSession, access_token: str) -> Device | None:
    device = await session.scalar(
        select(Device).where(Device.access_token_hash == hash_token(access_token))
    )
    if device is None or device.status != "active":
        return None
    if device.token_expires_at and utcnow() > as_utc(device.token_expires_at):
        return None
    device.last_seen_at = utcnow()
    await session.commit()
    return device


async def revoke_device(session: AsyncSession, device_id: str) -> bool:
    device = await session.get(Device, device_id)
    if device is None:
        return False
    device.status = "revoked"
    device.access_token_hash = None
    device.provisioning_token_hash = None
    await session.commit()
    return True
