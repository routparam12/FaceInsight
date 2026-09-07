from fastapi import APIRouter

from app.api.v1 import (
    attendance,
    auth,
    devices,
    employees,
    enrollment,
    gallery,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(devices.router)
api_router.include_router(employees.router)
api_router.include_router(enrollment.router)
api_router.include_router(gallery.router)
api_router.include_router(attendance.router)
