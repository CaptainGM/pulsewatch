from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.models import User, utcnow
from app.schemas import AuthConfigOut, LoginIn, LoginOut, UserOut
from app.security import (
    create_access_token,
    create_oauth_state,
    decode_access_token,
    require_user,
    verify_oauth_state,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def google_enabled() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def _http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=10)


def _user_out(user: User, demo: bool = False) -> UserOut:
    return UserOut(email=user.email, name=user.name, demo=demo, role=user.role)


def _oauth_redirect(fragment: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.public_url.rstrip('/')}/#{fragment}", status_code=302)


@router.get("/config", response_model=AuthConfigOut)
async def auth_config():
    return AuthConfigOut(
        enabled=settings.auth_enabled,
        demo=not settings.auth_enabled,
        workspace_name=settings.workspace_name,
        version=settings.version,
        google=google_enabled(),
    )


@router.post("/login", response_model=LoginOut)
async def login(payload: LoginIn, session: AsyncSession = Depends(get_session)):
    user = await session.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if user is None or not user.active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-posta veya şifre hatalı",
        )
    user.last_login_at = utcnow()
    await session.commit()
    token, expires_at = create_access_token(user.email, role=user.role, name=user.name)
    return LoginOut(
        access_token=token,
        expires_at=expires_at,
        user=_user_out(user, demo=not settings.auth_enabled),
    )


@router.get("/me", response_model=UserOut)
async def me(current: dict = Depends(require_user)):
    return UserOut(
        email=str(current.get("sub")),
        name=str(current.get("name") or "Yönetici"),
        demo=bool(current.get("demo")),
        role=str(current.get("role") or "viewer"),
    )


@router.get("/verify")
async def verify(token: str):
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {"valid": True, "subject": payload.get("sub"), "exp": payload.get("exp")}


@router.get("/google/login")
async def google_login():
    if not google_enabled():
        raise HTTPException(status_code=404, detail="Google girişi etkin değil")
    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": f"{settings.public_url.rstrip('/')}/api/auth/google/callback",
            "response_type": "code",
            "scope": "openid email profile",
            "state": create_oauth_state(),
            "prompt": "select_account",
        }
    )
    return RedirectResponse(f"{settings.google_auth_url}?{query}", status_code=302)


@router.get("/google/callback")
async def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    if error or not code or not state or not verify_oauth_state(state):
        return _oauth_redirect("oauth_error=state")

    async with _http_client() as client:
        token_response = await client.post(
            settings.google_token_url,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": f"{settings.public_url.rstrip('/')}/api/auth/google/callback",
                "grant_type": "authorization_code",
            },
        )
        if token_response.status_code != 200:
            return _oauth_redirect("oauth_error=token")
        access_token = token_response.json().get("access_token")
        if not access_token:
            return _oauth_redirect("oauth_error=token")

        info_response = await client.get(
            settings.google_userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if info_response.status_code != 200:
        return _oauth_redirect("oauth_error=profile")
    info = info_response.json()

    email = str(info.get("email") or "").strip().lower()
    if not email or info.get("email_verified") is not True:
        return _oauth_redirect("oauth_error=unverified")

    allowed = [
        item.strip().lower() for item in settings.oauth_allowed_domains.split(",") if item.strip()
    ]
    if allowed and email.rsplit("@", 1)[-1] not in allowed:
        return _oauth_redirect("oauth_error=domain")

    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        if not settings.oauth_auto_create:
            return _oauth_redirect("oauth_error=not_registered")
        user = User(
            email=email,
            name=str(info.get("name") or email.split("@")[0])[:120],
            role="viewer",
            auth_provider="google",
            active=True,
        )
        session.add(user)
    elif not user.active:
        return _oauth_redirect("oauth_error=disabled")

    user.last_login_at = utcnow()
    await session.commit()
    token, _ = create_access_token(user.email, role=user.role, name=user.name)
    return _oauth_redirect(f"oauth_token={token}")
