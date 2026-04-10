"""CRUD-операции для инвайт-кодов."""

import random
import string

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Invite, User

logger = structlog.get_logger(__name__)


def _generate_code(length: int = 10) -> str:
    """Генерация случайного кода из заглавных букв и цифр."""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(random.choices(alphabet, k=length))


async def create_invite(db: AsyncSession, created_by: int) -> Invite:
    """Создание нового инвайта с уникальным кодом."""
    # Генерируем уникальный код, проверяя на дубликаты
    while True:
        code = _generate_code()
        existing = await get_invite(db, code)
        if existing is None:
            break

    invite = Invite(code=code, created_by=created_by)
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite


async def get_invite(db: AsyncSession, code: str) -> Invite | None:
    """Получение инвайта по коду."""
    result = await db.execute(select(Invite).where(Invite.code == code))
    return result.scalar_one_or_none()


async def activate_invite(db: AsyncSession, code: str, user_id: int) -> tuple[bool, str]:
    """
    Активация инвайта.

    Проверяет:
    - Существование инвайта
    - Не использован ли уже
    - Не забанен ли пользователь

    Returns:
        tuple[bool, str]: (успех, сообщение)
    """
    invite = await get_invite(db, code)
    if invite is None:
        return False, 'Инвайт-код не найден'

    if invite.used_by is not None:
        return False, 'Инвайт-код уже использован'

    # Проверяем, не забанен ли пользователь
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        return False, 'Пользователь не найден'

    if user.is_banned:
        return False, 'Пользователь заблокирован'

    # Активируем инвайт
    from datetime import UTC, datetime

    invite.used_by = user_id
    invite.used_at = datetime.now(UTC)
    user.invite_activated = True

    await db.commit()
    return True, 'Инвайт-код успешно активирован'


async def get_user_invites(db: AsyncSession, user_id: int) -> list[Invite]:
    """Список инвайтов, созданных пользователем."""
    result = await db.execute(select(Invite).where(Invite.created_by == user_id))
    return list(result.scalars().all())


async def get_all_invites(db: AsyncSession) -> list[Invite]:
    """Все инвайты (для администратора)."""
    result = await db.execute(select(Invite))
    return list(result.scalars().all())


async def deactivate_user_invite(db: AsyncSession, user_id: int) -> None:
    """
    Деактивация подписки пользователя по инвайту.
    Если у пользователя бессрочная подписка (is_permanent) — пропускает.
    """
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        return

    if user.is_permanent:
        return

    user.invite_activated = False
    await db.commit()


async def ban_user(db: AsyncSession, user_id: int) -> None:
    """Блокировка пользователя: is_banned=True, invite_activated=False."""
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        return

    user.is_banned = True
    user.invite_activated = False
    await db.commit()


async def unban_user(db: AsyncSession, user_id: int) -> None:
    """Разблокировка пользователя: is_banned=False. Подписки НЕ восстанавливаются."""
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        return

    user.is_banned = False
    await db.commit()


async def set_permanent(db: AsyncSession, user_id: int, value: bool) -> None:
    """Установка/снятие бессрочной подписки."""
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        return

    user.is_permanent = value
    await db.commit()
