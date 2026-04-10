"""Роуты инвайт-системы для кабинета пользователя."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User

from ..dependencies import get_cabinet_db, get_current_cabinet_user

router = APIRouter(prefix='/invite', tags=['Cabinet Invite'])


# --- Схемы запросов/ответов ---


class ActivateInviteRequest(BaseModel):
    """Тело запроса на активацию инвайт-кода."""

    code: str


class ActivateInviteResponse(BaseModel):
    """Ответ на успешную активацию инвайта."""

    success: bool


class GenerateInviteResponse(BaseModel):
    """Ответ с новым сгенерированным инвайт-кодом."""

    code: str


class MyInviteItem(BaseModel):
    """Элемент списка инвайтов пользователя."""

    code: str
    used_by_username: str | None = None
    used_at: datetime | None = None
    created_at: datetime


# --- Эндпоинты ---


@router.post('/activate', response_model=ActivateInviteResponse)
async def activate_invite(
    body: ActivateInviteRequest,
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Активация инвайт-кода текущим пользователем."""
    # Проверка бана
    if user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='User is banned',
        )

    # Проверка: инвайт уже активирован ранее
    if user.invite_activated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Invite already activated',
        )

    from app.database.crud.invites import activate_invite as do_activate

    success, message = await do_activate(db, body.code.strip().upper(), user.id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )
    return ActivateInviteResponse(success=True)


@router.post('/generate', response_model=GenerateInviteResponse)
async def generate_invite(
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Генерация нового инвайт-кода для текущего пользователя."""
    # Проверка бана
    if user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='User is banned',
        )

    # Только пользователи с активированным инвайтом могут генерировать коды
    if not user.invite_activated:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Invite not activated',
        )

    from app.database.crud.invites import create_invite

    invite = await create_invite(db, user.id)
    return GenerateInviteResponse(code=invite.code)


@router.get('/my', response_model=list[MyInviteItem])
async def get_my_invites(
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Получение списка инвайтов, созданных текущим пользователем."""
    from app.database.crud.invites import get_user_invites

    invites = await get_user_invites(db, user.id)
    return [
        MyInviteItem(
            code=inv.code,
            used_by_username=None,  # TODO: join user для получения username
            used_at=inv.used_at,
            created_at=inv.created_at,
        )
        for inv in invites
    ]
