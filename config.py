from functools import lru_cache
import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    google_application_credentials: str | None = None
    security_disable_semantic: bool = False
    admin_email: str = "admin@shield.local"
    admin_password: str = "SecureAdmin123!"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.google_application_credentials:
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", s.google_application_credentials)
    return s
