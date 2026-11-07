import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.models import ApiKey, User, utcnow

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt.encode("ascii"),
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return f"scrypt${salt}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algorithm, salt, digest = stored.split("$", 2)
    except ValueError:
        return False
    if algorithm != "scrypt":
        return False
    candidate = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt.encode("ascii"),
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return hmac.compare_digest(candidate.hex(), digest)


def _sign(payload: dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    segments = [
        _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
        _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    ]
    signing_input = ".".join(segments).encode("ascii")
    signature = hmac.new(
        settings.jwt_secret.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    return f"{'.'.join(segments)}.{_b64encode(signature)}"


def create_access_token(
    subject: str,
    role: str = "admin",
    name: str = "Yönetici",
    minutes: int | None = None,
) -> tuple[str, datetime]:
    expires_at = utcnow().replace(microsecond=0) + timedelta(
        minutes=minutes or settings.access_token_minutes
    )
    payload = {
        "sub": subject,
        "role": role,
        "name": name,
        "iat": int(time.time()),
        "exp": int(expires_at.timestamp()),
    }
    return _sign(payload), expires_at


def create_oauth_state() -> str:
    return _sign(
        {
            "typ": "oauth_state",
            "nonce": secrets.token_urlsafe(16),
            "exp": int(time.time()) + 600,
        }
    )


def verify_oauth_state(state: str) -> bool:
    try:
        payload = decode_access_token(state)
    except ValueError:
        return False
    return payload.get("typ") == "oauth_state"


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise ValueError("Geçersiz token") from exc
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(settings.jwt_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _b64decode(signature_b64)):
        raise ValueError("Token imzası geçersiz")
    payload = json.loads(_b64decode(payload_b64))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("Token süresi doldu")
    return payload


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


async def require_user(
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not settings.auth_enabled:
        return {"sub": settings.admin_email, "name": "Demo yönetici", "role": "admin", "demo": True}

    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bu işlem için giriş yapmalısınız",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await session.scalar(select(User).where(User.email == payload.get("sub")))
    if user is None or not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Oturum geçersiz, yeniden giriş yapın",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if request.method not in SAFE_METHODS and user.role != "admin":
        raise HTTPException(status_code=403, detail="Bu işlem için yönetici yetkisi gerekir")
    return {"sub": user.email, "name": user.name, "role": user.role, "demo": False}


async def require_admin(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Bu sayfa yalnızca yöneticilere açık")
    return user


def generate_api_key() -> tuple[str, str, str]:
    secret = secrets.token_urlsafe(32)
    full = f"pw_live_{secret}"
    prefix = full[:16]
    return full, prefix, hashlib.sha256(full.encode("utf-8")).hexdigest()


async def _api_key_principal(session: AsyncSession, raw: str) -> dict[str, Any] | None:
    key_hash = hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()
    api_key = await session.scalar(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None))
    )
    if api_key is None:
        return None
    await session.execute(
        update(ApiKey).where(ApiKey.id == api_key.id).values(last_used_at=utcnow())
    )
    await session.commit()
    return {"sub": f"api-key:{api_key.id}", "name": api_key.name, "api_key_id": api_key.id}


async def require_api_access(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if x_api_key:
        principal = await _api_key_principal(session, x_api_key)
        if principal is None:
            raise HTTPException(status_code=401, detail="API anahtarı geçersiz")
        return principal

    token = _bearer_token(authorization)
    if token:
        principal = await _api_key_principal(session, token)
        if principal is not None:
            return principal
        if settings.auth_enabled:
            try:
                return decode_access_token(token)
            except ValueError as exc:
                raise HTTPException(status_code=401, detail=str(exc)) from exc

    raise HTTPException(
        status_code=401,
        detail="X-API-Key başlığı ile geçerli bir API anahtarı gönderin",
    )


async def require_ws_access(token: str | None) -> bool:
    if not settings.auth_enabled:
        return True
    if not token:
        return False
    try:
        decode_access_token(token)
    except ValueError:
        return False
    return True
