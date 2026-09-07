from datetime import time

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import AdminDep, SessionDep
from app.models.employee import Employee
from app.services import gallery_service

router = APIRouter(prefix="/employees", tags=["employees"])


class EmployeeUpsert(BaseModel):
    id: str
    name: str
    site_id: str
    timezone: str = "UTC"
    shift_start: time | None = None
    shift_end: time | None = None
    active: bool = True


class EmployeeRow(BaseModel):
    id: str
    name: str
    site_id: str
    timezone: str
    shift_start: time | None
    shift_end: time | None
    active: bool

    model_config = {"from_attributes": True}


@router.post("", response_model=EmployeeRow, status_code=status.HTTP_201_CREATED)
async def create_employee(body: EmployeeUpsert, session: SessionDep, _: AdminDep):
    if await session.get(Employee, body.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "employee id already exists")
    emp = Employee(**body.model_dump())
    session.add(emp)
    await session.commit()
    await session.refresh(emp)
    return emp


@router.get("", response_model=list[EmployeeRow])
async def list_employees(session: SessionDep, _: AdminDep, site_id: str | None = None):
    stmt = select(Employee)
    if site_id:
        stmt = stmt.where(Employee.site_id == site_id)
    return list(await session.scalars(stmt.order_by(Employee.id)))


@router.get("/{employee_id}", response_model=EmployeeRow)
async def get_employee(employee_id: str, session: SessionDep, _: AdminDep):
    emp = await session.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return emp


@router.post("/{employee_id}/deactivate", response_model=EmployeeRow)
async def deactivate_employee(employee_id: str, session: SessionDep, _: AdminDep):
    emp = await session.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    emp.active = False
    # Tombstone into the gallery log so devices drop this person on next sync.
    await gallery_service.record_change(
        session,
        employee_id=emp.id,
        site_id=emp.site_id,
        op="remove",
        model_version="",
    )
    await session.commit()
    await session.refresh(emp)
    return emp
