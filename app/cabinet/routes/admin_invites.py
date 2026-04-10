"""Админские маршруты для управления инвайтами и пользователями."""

import secrets
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Invite, User

from ..dependencies import get_cabinet_db, require_permission


logger = structlog.get_logger(__name__)

router = APIRouter(prefix='/admin/invites', tags=['Cabinet Admin Invites'])


# --- Схемы ---


class InviteOut(BaseModel):
    """Схема инвайта для ответа."""

    code: str
    created_by: int
    used_by: int | None = None
    used_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class SetPermanentRequest(BaseModel):
    """Запрос на установку/снятие бессрочной подписки."""

    value: bool


class MessageResponse(BaseModel):
    """Простой ответ с сообщением."""

    message: str


# --- Эндпоинты для инвайтов ---


@router.get('', response_model=list[InviteOut])
async def list_invites(
    _admin: User = Depends(require_permission('invites:read')),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Получить список всех инвайтов."""
    result = await db.execute(select(Invite).order_by(Invite.created_at.desc()))
    invites = result.scalars().all()
    return invites


@router.post('/generate', response_model=InviteOut)
async def generate_invite(
    user_id: int = Query(..., description='ID пользователя, от имени которого генерируется инвайт'),
    _admin: User = Depends(require_permission('invites:write')),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Генерация инвайт-кода от имени указанного пользователя."""
    # Проверяем, что пользователь существует
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Пользователь с id={user_id} не найден',
        )

    # Генерируем уникальный код
    code = secrets.token_urlsafe(12)[:16]

    invite = Invite(
        code=code,
        created_by=user_id,
        created_at=datetime.now(UTC),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    logger.info('Админ сгенерировал инвайт', code=code, user_id=user_id)
    return invite


@router.delete('/{code}', response_model=MessageResponse)
async def delete_invite(
    code: str,
    _admin: User = Depends(require_permission('invites:write')),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Удаление неиспользованного инвайта."""
    invite = await db.get(Invite, code)
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Инвайт с кодом {code} не найден',
        )

    # Нельзя удалить использованный инвайт
    if invite.used_by is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Невозможно удалить использованный инвайт',
        )

    await db.delete(invite)
    await db.commit()

    logger.info('Админ удалил инвайт', code=code)
    return MessageResponse(message=f'Инвайт {code} удалён')


# --- Эндпоинты для управления пользователями ---

users_router = APIRouter(prefix='/admin/users', tags=['Cabinet Admin Invites Users'])


@users_router.post('/{user_id}/set-permanent', response_model=MessageResponse)
async def set_permanent_subscription(
    user_id: int,
    body: SetPermanentRequest,
    _admin: User = Depends(require_permission('users:write')),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Установка или снятие бессрочной подписки пользователя."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Пользователь с id={user_id} не найден',
        )

    user.is_permanent = body.value
    await db.commit()

    action = 'установлена' if body.value else 'снята'
    logger.info('Бессрочная подписка изменена', user_id=user_id, value=body.value)
    return MessageResponse(message=f'Бессрочная подписка {action} для пользователя {user_id}')


@users_router.post('/{user_id}/ban', response_model=MessageResponse)
async def ban_user(
    user_id: int,
    _admin: User = Depends(require_permission('users:write')),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Бан пользователя: устанавливает is_banned=True, invite_activated=False."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Пользователь с id={user_id} не найден',
        )

    user.is_banned = True
    user.invite_activated = False
    # TODO: деактивировать VPN-подписки пользователя
    await db.commit()

    logger.info('Пользователь забанен', user_id=user_id)
    return MessageResponse(message=f'Пользователь {user_id} забанен')


@users_router.post('/{user_id}/unban', response_model=MessageResponse)
async def unban_user(
    user_id: int,
    _admin: User = Depends(require_permission('users:write')),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Разбан пользователя: устанавливает только is_banned=False (без восстановления остального)."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Пользователь с id={user_id} не найден',
        )

    user.is_banned = False
    await db.commit()

    logger.info('Пользователь разбанен', user_id=user_id)
    return MessageResponse(message=f'Пользователь {user_id} разбанен')
