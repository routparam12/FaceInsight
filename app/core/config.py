from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_name: str = "face-attendance"
    env: str = "dev"
    log_level: str = "INFO"

    # Database
    database_url: str = "sqlite+aiosqlite:///./face_attendance.db"

    # Admin auth
    admin_username: str = "admin"
    admin_password: str = "change-me"
    jwt_secret: str = "dev-only-change-me"
    jwt_ttl_minutes: int = 720

    # Device auth
    device_token_ttl_days: int = 90

    # Face model
    model_version: str = "arcface-v1"
    embedding_dim: int = 512
    face_model_path: str = ""

    # Recognition thresholds (cosine similarity, embeddings are L2-normalised)
    accept_threshold: float = 0.42
    review_low_threshold: float = 0.36
    collision_threshold: float = 0.42
    collision_margin: float = 0.05

    # Quality gates
    min_face_score: float = 0.60
    min_liveness_score: float = 0.70

    # Attendance rules
    clock_skew_seconds: int = 120
    debounce_seconds: int = 180
    shift_grace_minutes: int = 60
    enforce_shift_window: bool = False
    enforce_site_match: bool = True

    # Enrollment image storage
    storage_dir: str = "./app/storage/enrollment"
    enrollment_encryption_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
