from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.core.security import create_admin_token, verify_admin_credentials
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    if not verify_admin_credentials(body.username, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad credentials")
    return TokenResponse(
        access_token=create_admin_token(body.username),
        expires_in=settings.jwt_ttl_minutes * 60,
    )
