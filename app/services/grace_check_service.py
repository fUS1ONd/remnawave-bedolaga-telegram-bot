"""Сервис проверки истечения grace-периода.

Раз в час проверяет пользователей с grace_until < now()
и invite_activated = True — кикает из кабинета.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from sqlalchemy import and_, select

from app.database.models import User


logger = structlog.get_logger(__name__)

# Интервал проверки — раз в час
CHECK_INTERVAL_SECONDS = 3600


class GraceCheckService:
    """Периодическая проверка истечения grace-периода."""

    def __init__(self, session_factory):
        self._session_factory = session_factory
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Запустить сервис."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info('GraceCheckService запущен')

    async def stop(self) -> None:
        """Остановить сервис."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info('GraceCheckService остановлен')

    async def _loop(self) -> None:
        """Основной цикл — проверка раз в час."""
        while self._running:
            try:
                await self._check_expired_grace()
            except Exception:
                logger.exception('Ошибка в GraceCheckService')
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    async def _check_expired_grace(self) -> None:
        """Найти пользователей с истёкшим grace и деактивировать доступ."""
        now = datetime.now(UTC)

        async with self._session_factory() as db:
            # Ищем пользователей у которых grace_until прошёл, но invite_activated ещё True
            result = await db.execute(
                select(User).where(
                    and_(
                        User.grace_until.isnot(None),
                        User.grace_until < now,
                        User.invite_activated.is_(True),
                        User.is_permanent.is_(False),
                        User.is_banned.is_(False),
                    )
                )
            )
            users = list(result.scalars().all())

            if not users:
                return

            for user in users:
                user.invite_activated = False
                user.grace_until = None
                logger.info('Grace-период истёк — кик из кабинета', user_id=user.id)

            await db.commit()
            logger.info('GraceCheckService: деактивировано пользователей', count=len(users))
