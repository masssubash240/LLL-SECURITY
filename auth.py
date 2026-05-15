from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from config import get_settings

# pbkdf2_sha256 avoids bcrypt/passlib backend issues on some Python versions (e.g. 3.14 + bcrypt 4.x).
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def create_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


async def get_current_user_optional(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, Any] | None:
    if creds is None:
        return None
    try:
        payload = decode_token(creds.credentials)
        sub = payload.get("sub")
        if not sub:
            return None
        return {"email": sub, "role": payload.get("role", "user")}
    except JWTError:
        return None


async def require_admin(
    user: dict | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


async def require_user(
    user: dict | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user
