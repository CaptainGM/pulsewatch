from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import User
from app.schemas import UserCreate, UserListOut, UserUpdate
from app.security import hash_password, require_admin
from app.services.users import other_active_admins

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserListOut])
async def list_users(session: AsyncSession = Depends(get_session)):
    rows = await session.execute(select(User).order_by(User.created_at))
    return rows.scalars().all()


@router.post("", response_model=UserListOut, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, session: AsyncSession = Depends(get_session)):
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="Geçerli bir e-posta girin")
    if await session.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Bu e-posta ile kayıtlı bir kullanıcı var")
    user = User(
        email=email,
        name=payload.name.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        auth_provider="local",
        active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserListOut)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    current: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")

    losing_admin = (
        user.active
        and user.role == "admin"
        and (payload.active is False or payload.role == "viewer")
    )
    if losing_admin:
        if user.email == current.get("sub"):
            raise HTTPException(
                status_code=400, detail="Kendi yetkinizi düşüremez veya pasifleştiremezsiniz"
            )
        if await other_active_admins(session, user.id) == 0:
            raise HTTPException(status_code=400, detail="Sistemde en az bir aktif yönetici kalmalı")

    if payload.name is not None:
        user.name = payload.name.strip()
    if payload.role is not None:
        user.role = payload.role
    if payload.active is not None:
        user.active = payload.active
    if payload.password:
        user.password_hash = hash_password(payload.password)
    await session.commit()
    await session.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    if user.email == current.get("sub"):
        raise HTTPException(status_code=400, detail="Kendi hesabınızı silemezsiniz")
    if user.active and user.role == "admin" and await other_active_admins(session, user.id) == 0:
        raise HTTPException(status_code=400, detail="Sistemde en az bir aktif yönetici kalmalı")
    await session.delete(user)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
