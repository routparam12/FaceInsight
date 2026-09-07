from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import AdminDep, SessionDep
from app.models.device import Device
from app.services import device_service

router = APIRouter(prefix="/devices", tags=["devices"])


class CreateDeviceRequest(BaseModel):
    name: str
    site_id: str


class CreateDeviceResponse(BaseModel):
    device_id: str
    name: str
    site_id: str
    provisioning_token: str  # one-time; exchange at /devices/activate


class ActivateRequest(BaseModel):
    provisioning_token: str


class ActivateResponse(BaseModel):
    device_id: str
    access_token: str  # shown once
    token_type: str = "bearer"
    expires_in: int


class DeviceRow(BaseModel):
    id: str
    name: str
    site_id: str
    status: str

    model_config = {"from_attributes": True}


@router.post("", response_model=CreateDeviceResponse, status_code=status.HTTP_201_CREATED)
async def create_device(body: CreateDeviceRequest, session: SessionDep, _: AdminDep):
    created = await device_service.create_device(session, body.name, body.site_id)
    return CreateDeviceResponse(
        device_id=created.device.id,
        name=created.device.name,
        site_id=created.device.site_id,
        provisioning_token=created.provisioning_token,
    )


@router.post("/activate", response_model=ActivateResponse)
async def activate_device(body: ActivateRequest, session: SessionDep):
    activated = await device_service.activate_device(session, body.provisioning_token)
    if activated is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid provisioning token")
    return ActivateResponse(
        device_id=activated.device.id,
        access_token=activated.access_token,
        expires_in=activated.expires_in,
    )


@router.get("", response_model=list[DeviceRow])
async def list_devices(session: SessionDep, _: AdminDep):
    rows = await session.scalars(select(Device).order_by(Device.created_at.desc()))
    return list(rows)


@router.post("/{device_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_device(device_id: str, session: SessionDep, _: AdminDep):
    if not await device_service.revoke_device(session, device_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "device not found")
