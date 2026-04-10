# Invite System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Добавить систему инвайт-кодов в bedolaga — закрытая регистрация через одноразовые коды, фейковый лендинг диванного магазина как публичная морда сайта. Бессрочные подписки для своих, бан для нарушителей.

**Architecture:** Новая таблица `invites` + поля `invite_activated`, `is_permanent`, `is_banned` на пользователе. Бэкенд проверяет код при регистрации и активации. Фронтенд показывает диванный лендинг всем без активного кода, при наличии кода — редирект в ЛК.

**Tech Stack:** Python/FastAPI + SQLAlchemy + Alembic (backend), React/TypeScript + Zustand + React Router (frontend)

---

## Контекст проекта

### Репозитории
- **Backend:** `remnawave-bedolaga-telegram-bot` — FastAPI сервер, PostgreSQL, SQLAlchemy ORM
- **Frontend:** `bedolaga-cabinet` — React + TypeScript + Tailwind, Zustand для стейта

### Ключевые файлы backend
- `app/database/models.py` — все SQLAlchemy модели
- `app/cabinet/routes/auth.py` — регистрация: `register_email_standalone()` на строке ~971
- `app/cabinet/routes/__init__.py` — сюда добавлять импорты новых роутеров
- `app/webapi/app.py` — точка входа FastAPI, подключает `cabinet_router`
- `app/webapi/dependencies.py` — dependency injection (get_current_user, get_cabinet_db)
- `migrations/alembic/versions/` — последняя миграция: `0053_include_limited_in_unique_active_index.py`

### Ключевые файлы frontend
- `src/App.tsx` — роутинг (React Router, lazy load)
- `src/store/auth.ts` — Zustand стор, `AuthState` с `user`, `isAuthenticated`
- `src/api/auth.ts` — `registerEmailStandalone()` принимает `referral_code?: string`
- `src/pages/Login.tsx` — форма входа/регистрации

### Модель User (релевантные поля)
```python
auth_type = Column(String(20), default='telegram')
status = Column(String(20), default=UserStatus.ACTIVE.value)
referred_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
# invite_activated, is_permanent, is_banned — добавим в Task 1
```

### Состояния пользователя
| Состояние | Что видит |
|---|---|
| Не залогинен | Диванный лендинг + кнопка "Войти" |
| Залогинен, `invite_activated=False` | Диванный лендинг + кнопка "Выйти" + поле промокода внизу |
| Залогинен, `invite_activated=True` | Редирект в `/dashboard` |
| Залогинен, `is_banned=True` | Диванный лендинг + промокод (но активация отклоняется) |

### Приоритет флагов
| `is_permanent` | `is_banned` | Результат |
|---|---|---|
| false | false | Обычный пользователь, подчиняется сроку подписки |
| true | false | Бессрочная подписка, кик по истечению не срабатывает |
| любое | true | Заблокирован: нет доступа к ЛК, VPN отключен |

---

## Task 1: Alembic миграция — таблица invites + поля пользователя

**Files:**
- Create: `migrations/alembic/versions/0054_add_invites_system.py`

**Step 1: Создать файл миграции**

```python
"""add invites system

Revision ID: 0054
Revises: 0053
Create Date: 2026-04-11
"""

from typing import Union
import sqlalchemy as sa
from alembic import op

revision: str = '0054'
down_revision: Union[str, None] = '0053'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем поля к users
    op.add_column(
        'users',
        sa.Column('invite_activated', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.add_column(
        'users',
        sa.Column('is_permanent', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.add_column(
        'users',
        sa.Column('is_banned', sa.Boolean(), nullable=False, server_default='false'),
    )

    # Создаём таблицу invites
    op.create_table(
        'invites',
        sa.Column('code', sa.String(16), primary_key=True),
        sa.Column(
            'created_by',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'used_by',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
    )

    op.create_index('ix_invites_created_by', 'invites', ['created_by'])
    op.create_index('ix_invites_used_by', 'invites', ['used_by'])


def downgrade() -> None:
    op.drop_index('ix_invites_used_by', table_name='invites')
    op.drop_index('ix_invites_created_by', table_name='invites')
    op.drop_table('invites')
    op.drop_column('users', 'is_banned')
    op.drop_column('users', 'is_permanent')
    op.drop_column('users', 'invite_activated')
```

**Step 2: Применить миграцию**

```bash
cd /home/krivonosov/projects/remnawave-bedolaga-telegram-bot
alembic upgrade head
```

Ожидаем: `Running upgrade 0053 -> 0054, add invites system`

**Step 3: Commit**

```bash
git add migrations/alembic/versions/0054_add_invites_system.py
git commit -m "feat: add invites migration (table + user fields)"
```

---

## Task 2: SQLAlchemy модель Invite + поля в User

**Files:**
- Modify: `app/database/models.py`

**Step 1: Добавить поля в модель User**

Найти класс `User` в `app/database/models.py`. После поля `referred_by_id` добавить:

```python
invite_activated = Column(Boolean, nullable=False, default=False, server_default='false')
is_permanent = Column(Boolean, nullable=False, default=False, server_default='false')
is_banned = Column(Boolean, nullable=False, default=False, server_default='false')
```

**Step 2: Добавить модель Invite**

В конец файла `app/database/models.py` добавить:

```python
class Invite(Base):
    __tablename__ = 'invites'

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True
    )
    used_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True
    )
    used_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        AwareDateTime, nullable=False, server_default=func.now()
    )

    # Relationships
    creator: Mapped['User'] = relationship('User', foreign_keys=[created_by])
    user: Mapped['User | None'] = relationship('User', foreign_keys=[used_by])
```

> Примечание: `AwareDateTime` уже используется в проекте — посмотри как импортируется в других моделях, например `Subscription`.

**Step 3: Проверить что импорты корректны**

```bash
cd /home/krivonosov/projects/remnawave-bedolaga-telegram-bot
python -c "from app.database.models import Invite, User; print('OK')"
```

Ожидаем: `OK`

**Step 4: Commit**

```bash
git add app/database/models.py
git commit -m "feat: add Invite model and user fields (invite_activated, is_permanent, is_banned)"
```

---

## Task 3: CRUD функции для инвайтов

**Files:**
- Create: `app/database/crud/invites.py`

**Step 1: Создать файл**

```python
"""CRUD операции для инвайтов."""

import secrets
import string
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Invite, User


def _generate_code(length: int = 10) -> str:
    """Генерирует случайный код из букв и цифр."""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


async def create_invite(db: AsyncSession, created_by: int) -> Invite:
    """Создаёт новый инвайт-код для пользователя."""
    # Генерируем уникальный код
    for _ in range(10):  # максимум 10 попыток на случай коллизии
        code = _generate_code()
        existing = await db.get(Invite, code)
        if existing is None:
            break
    else:
        raise RuntimeError('Не удалось сгенерировать уникальный код')

    invite = Invite(code=code, created_by=created_by)
    db.add(invite)
    await db.flush()
    await db.refresh(invite)
    return invite


async def get_invite(db: AsyncSession, code: str) -> Invite | None:
    """Возвращает инвайт по коду."""
    return await db.get(Invite, code.upper())


async def activate_invite(
    db: AsyncSession, code: str, user_id: int
) -> tuple[bool, str]:
    """
    Активирует инвайт для пользователя.

    Returns:
        (True, '') при успехе
        (False, причина) при ошибке
    """
    # Проверяем бан
    user = await db.get(User, user_id)
    if user is None:
        return False, 'Пользователь не найден'
    if user.is_banned:
        return False, 'Аккаунт заблокирован'

    invite = await get_invite(db, code)

    if invite is None:
        return False, 'Код не найден'

    if invite.used_by is not None:
        return False, 'Код уже использован'

    # Атомарно помечаем инвайт как использованный
    invite.used_by = user_id
    invite.used_at = datetime.now(timezone.utc)

    # Активируем пользователя
    user.invite_activated = True

    await db.flush()
    return True, ''


async def get_user_invites(db: AsyncSession, user_id: int) -> list[Invite]:
    """Возвращает все инвайты созданные пользователем."""
    result = await db.execute(
        select(Invite).where(Invite.created_by == user_id).order_by(Invite.created_at.desc())
    )
    return list(result.scalars().all())


async def get_all_invites(db: AsyncSession) -> list[Invite]:
    """Возвращает все инвайты (для admin)."""
    result = await db.execute(select(Invite).order_by(Invite.created_at.desc()))
    return list(result.scalars().all())


async def deactivate_user_invite(db: AsyncSession, user_id: int) -> None:
    """Деактивирует доступ пользователя (кик при неоплате)."""
    user = await db.get(User, user_id)
    if user and not user.is_permanent:
        user.invite_activated = False
        await db.flush()


async def ban_user(db: AsyncSession, user_id: int) -> bool:
    """
    Банит пользователя: is_banned=True, invite_activated=False.
    Деактивация VPN-подписок — вызывается отдельно.

    Returns:
        True если пользователь найден и забанен
    """
    user = await db.get(User, user_id)
    if user is None:
        return False
    user.is_banned = True
    user.invite_activated = False
    await db.flush()
    return True


async def unban_user(db: AsyncSession, user_id: int) -> bool:
    """
    Разбанивает пользователя: только is_banned=False.
    invite_activated и подписки НЕ восстанавливаются.

    Returns:
        True если пользователь найден и разбанен
    """
    user = await db.get(User, user_id)
    if user is None:
        return False
    user.is_banned = False
    await db.flush()
    return True


async def set_permanent(db: AsyncSession, user_id: int, value: bool) -> bool:
    """
    Устанавливает/снимает бессрочную подписку.

    Returns:
        True если пользователь найден
    """
    user = await db.get(User, user_id)
    if user is None:
        return False
    user.is_permanent = value
    await db.flush()
    return True
```

**Step 2: Проверить импорт**

```bash
python -c "from app.database.crud.invites import create_invite, ban_user, set_permanent; print('OK')"
```

Ожидаем: `OK`

**Step 3: Commit**

```bash
git add app/database/crud/invites.py
git commit -m "feat: add invite CRUD functions (with ban/permanent support)"
```

---

## Task 4: API роутер для инвайтов (пользовательский)

**Files:**
- Create: `app/cabinet/routes/invite.py`
- Modify: `app/cabinet/routes/__init__.py`

**Step 1: Создать роутер**

```python
"""API эндпоинты для системы инвайтов."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud.invites import (
    activate_invite,
    create_invite,
    get_user_invites,
)
from app.database.models import User
from app.webapi.dependencies import get_cabinet_db, get_current_user

router = APIRouter(prefix='/invite', tags=['invite'])


class ActivateInviteRequest(BaseModel):
    code: str


class InviteResponse(BaseModel):
    code: str
    used_by_username: str | None
    used_at: str | None
    created_at: str


class ActivateInviteResponse(BaseModel):
    success: bool


@router.post('/activate', response_model=ActivateInviteResponse)
async def activate_invite_endpoint(
    data: ActivateInviteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Активирует инвайт-код для текущего пользователя."""
    if current_user.is_banned:
        raise HTTPException(status_code=403, detail='Аккаунт заблокирован')

    if current_user.invite_activated:
        raise HTTPException(status_code=400, detail='Доступ уже активирован')

    success, reason = await activate_invite(db, data.code.strip().upper(), current_user.id)

    if not success:
        raise HTTPException(status_code=400, detail=reason)

    await db.commit()
    return ActivateInviteResponse(success=True)


@router.post('/generate', response_model=dict)
async def generate_invite_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Генерирует новый инвайт-код. Доступно только пользователям с активным доступом."""
    if current_user.is_banned:
        raise HTTPException(status_code=403, detail='Аккаунт заблокирован')

    if not current_user.invite_activated:
        raise HTTPException(status_code=403, detail='Нет доступа')

    invite = await create_invite(db, current_user.id)
    await db.commit()
    return {'code': invite.code}


@router.get('/my', response_model=list[InviteResponse])
async def get_my_invites_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Возвращает все инвайты созданные текущим пользователем."""
    invites = await get_user_invites(db, current_user.id)
    return [
        InviteResponse(
            code=inv.code,
            used_by_username=inv.user.username if inv.user else None,
            used_at=inv.used_at.isoformat() if inv.used_at else None,
            created_at=inv.created_at.isoformat(),
        )
        for inv in invites
    ]
```

**Step 2: Зарегистрировать роутер в `app/cabinet/routes/__init__.py`**

Найти блок импортов и добавить:
```python
from .invite import router as invite_router
```

Найти блок `include_router` и добавить:
```python
router.include_router(invite_router)
```

> Как именно подключены другие роутеры — смотри существующие примеры в `__init__.py`, структура у всех одинаковая.

**Step 3: Проверить что роутер регистрируется**

```bash
python -c "from app.cabinet.routes.invite import router; print('OK')"
```

Ожидаем: `OK`

**Step 4: Commit**

```bash
git add app/cabinet/routes/invite.py app/cabinet/routes/__init__.py
git commit -m "feat: add invite API endpoints (activate, generate, list)"
```

---

## Task 5: Admin API для инвайтов + управление пользователями

**Files:**
- Create: `app/cabinet/routes/admin_invites.py`
- Modify: `app/cabinet/routes/__init__.py`

**Step 1: Создать admin роутер**

```python
"""Admin API для управления инвайтами и пользователями (бан, бессрочка)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.crud.invites import (
    ban_user,
    create_invite,
    get_all_invites,
    get_invite,
    set_permanent,
    unban_user,
)
from app.database.models import User
from app.webapi.dependencies import get_cabinet_db, get_current_admin_user

router = APIRouter(prefix='/admin', tags=['admin'])


class AdminInviteResponse(BaseModel):
    code: str
    created_by_id: int
    used_by_id: int | None
    used_at: str | None
    created_at: str


class SetPermanentRequest(BaseModel):
    value: bool


# --- Инвайты ---

@router.get('/invites', response_model=list[AdminInviteResponse])
async def list_invites(
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Список всех инвайтов."""
    invites = await get_all_invites(db)
    return [
        AdminInviteResponse(
            code=inv.code,
            created_by_id=inv.created_by,
            used_by_id=inv.used_by,
            used_at=inv.used_at.isoformat() if inv.used_at else None,
            created_at=inv.created_at.isoformat(),
        )
        for inv in invites
    ]


@router.post('/invites/generate', response_model=dict)
async def admin_generate_invite(
    user_id: int,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Генерирует инвайт от имени указанного пользователя (или от имени админа)."""
    invite = await create_invite(db, user_id)
    await db.commit()
    return {'code': invite.code}


@router.delete('/invites/{code}')
async def admin_delete_invite(
    code: str,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Удаляет инвайт (только если не использован)."""
    invite = await get_invite(db, code.upper())
    if invite is None:
        raise HTTPException(status_code=404, detail='Инвайт не найден')
    if invite.used_by is not None:
        raise HTTPException(status_code=400, detail='Нельзя удалить использованный инвайт')

    await db.delete(invite)
    await db.commit()
    return {'success': True}


# --- Управление пользователями ---

@router.post('/users/{user_id}/set-permanent', response_model=dict)
async def admin_set_permanent(
    user_id: int,
    data: SetPermanentRequest,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Устанавливает/снимает бессрочную подписку."""
    success = await set_permanent(db, user_id, data.value)
    if not success:
        raise HTTPException(status_code=404, detail='Пользователь не найден')
    await db.commit()
    return {'success': True, 'is_permanent': data.value}


@router.post('/users/{user_id}/ban', response_model=dict)
async def admin_ban_user(
    user_id: int,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """
    Банит пользователя:
    - is_banned = True
    - invite_activated = False
    - Все VPN-подписки деактивируются
    """
    success = await ban_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail='Пользователь не найден')

    # TODO: деактивировать VPN-подписки пользователя
    # Найти функцию деактивации подписок в проекте и вызвать здесь
    # Например: await disable_all_subscriptions(db, user_id)

    await db.commit()
    return {'success': True, 'banned': True}


@router.post('/users/{user_id}/unban', response_model=dict)
async def admin_unban_user(
    user_id: int,
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """
    Разбанивает пользователя.
    Только снимает is_banned. Подписки и invite_activated НЕ восстанавливаются.
    Для возврата доступа нужен новый инвайт-код.
    """
    success = await unban_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail='Пользователь не найден')
    await db.commit()
    return {'success': True, 'banned': False}
```

**Step 2: Зарегистрировать в `__init__.py`** — аналогично Task 4.

```python
from .admin_invites import router as admin_invites_router
# и router.include_router(admin_invites_router)
```

**Step 3: Commit**

```bash
git add app/cabinet/routes/admin_invites.py app/cabinet/routes/__init__.py
git commit -m "feat: add admin API (invites + ban + permanent)"
```

---

## Task 6: Проверка инвайта при регистрации

**Files:**
- Modify: `app/cabinet/routes/auth.py`

**Step 1: Добавить `invite_code` в `EmailRegisterStandaloneRequest`**

Найти класс `EmailRegisterStandaloneRequest` и добавить поле:

```python
invite_code: str | None = None
```

**Step 2: Добавить обработку инвайта в функцию `register_email_standalone`**

После строки создания пользователя (после `await db.flush()` или после создания объекта `User`) добавить:

```python
# Активация инвайта при регистрации (если передан)
if request.invite_code:
    from app.database.crud.invites import activate_invite
    success, reason = await activate_invite(db, request.invite_code.strip().upper(), new_user.id)
    # Не бросаем ошибку если код невалидный — просто регистрируем без активации
    # Неверный код не должен блокировать регистрацию
```

> Найди точное место вставки: ищи `db.add(user)` или `await db.flush()` после создания пользователя в `register_email_standalone`.

**Step 3: Проверить что регистрация работает**

```bash
# Запустить сервер и сделать тестовый запрос
curl -X POST http://localhost:8000/cabinet/auth/email/register/standalone \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "testpass123"}'
```

Ожидаем: ответ без ошибок (500 не должно быть).

**Step 4: Commit**

```bash
git add app/cabinet/routes/auth.py
git commit -m "feat: handle invite_code on email registration"
```

---

## Task 7: Frontend — диванный лендинг (HTML шаблон)

**Files:**
- Create: `public/landing/` — папка для HTML шаблона
- Create: `src/pages/Landing.tsx`

**Step 1: Найти шаблон**

Скачать бесплатный HTML шаблон мебельного магазина. Хороший вариант для поиска:
- `free furniture store HTML template` на сайтах: free-css.com, templatemo.com, html5up.net

Распаковать в `public/landing/index.html` (с CSS/JS/images рядом).

**Step 2: Создать React компонент Landing**

```tsx
// src/pages/Landing.tsx
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';

export default function Landing() {
  const navigate = useNavigate();
  const { isAuthenticated, user, logout, activateInvite } = useAuthStore();
  const [promoCode, setPromoCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Если пользователь уже с активированным инвайтом и не забанен — в ЛК
  useEffect(() => {
    if (isAuthenticated && user?.invite_activated && !user?.is_banned) {
      navigate('/dashboard');
    }
  }, [isAuthenticated, user, navigate]);

  const handleActivate = async () => {
    if (!promoCode.trim()) return;
    setLoading(true);
    setError('');
    try {
      await activateInvite(promoCode.trim());
      navigate('/dashboard');
    } catch (e: any) {
      // Бэкенд возвращает detail с причиной
      setError(e?.response?.data?.detail ?? 'Неверный код');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative">
      {/* Диванный лендинг через iframe */}
      <iframe
        src="/landing/index.html"
        className="w-full min-h-screen border-0"
        title="Магазин мебели"
      />

      {/* Кнопка выйти — только для залогиненных без активного кода */}
      {isAuthenticated && !user?.invite_activated && (
        <button
          onClick={logout}
          className="fixed top-4 right-4 z-50 text-sm text-gray-500 hover:text-gray-800"
        >
          Выйти
        </button>
      )}

      {/* Поле промокода — только для залогиненных без активного кода */}
      {isAuthenticated && !user?.invite_activated && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex flex-col items-center gap-1">
          <div className="flex gap-2">
            <input
              type="text"
              value={promoCode}
              onChange={(e) => setPromoCode(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleActivate()}
              placeholder="Промокод"
              className="border border-gray-300 rounded px-3 py-2 text-sm w-40 focus:outline-none focus:border-gray-500"
            />
            <button
              onClick={handleActivate}
              disabled={loading}
              className="border border-gray-300 rounded px-3 py-2 text-sm hover:bg-gray-50 disabled:opacity-50"
            >
              →
            </button>
          </div>
          {error && <span className="text-red-500 text-xs">{error}</span>}
        </div>
      )}
    </div>
  );
}
```

> Если iframe не подходит из-за CORS или стилей — можно сделать лендинг как обычную React страницу, скопировав HTML структуру шаблона в JSX.

**Step 3: Commit**

```bash
git add public/landing/ src/pages/Landing.tsx
git commit -m "feat: add furniture store landing page"
```

---

## Task 8: Frontend — стор и API

**Files:**
- Create: `src/api/invite.ts`
- Modify: `src/store/auth.ts`

**Step 1: Создать API клиент**

```typescript
// src/api/invite.ts
import { apiClient } from './client';

export interface InviteItem {
  code: string;
  used_by_username: string | null;
  used_at: string | null;
  created_at: string;
}

export const inviteApi = {
  activate: async (code: string): Promise<{ success: boolean }> => {
    const res = await apiClient.post('/cabinet/invite/activate', { code });
    return res.data;
  },

  generate: async (): Promise<{ code: string }> => {
    const res = await apiClient.post('/cabinet/invite/generate');
    return res.data;
  },

  myInvites: async (): Promise<InviteItem[]> => {
    const res = await apiClient.get('/cabinet/invite/my');
    return res.data;
  },
};
```

**Step 2: Добавить в стор поля и методы**

В `src/store/auth.ts`:

1. В интерфейс `User` добавить поля:
```typescript
invite_activated: boolean;
is_permanent: boolean;
is_banned: boolean;
```

2. В `AuthState` добавить метод:
```typescript
activateInvite: (code: string) => Promise<void>;
```

3. Реализовать метод в `create(...)`:
```typescript
activateInvite: async (code: string) => {
  await inviteApi.activate(code);
  // Обновляем данные пользователя
  const { fetchUser } = get();
  await fetchUser();
},
```

> `fetchUser` — метод который делает `GET /cabinet/users/me` и обновляет `user` в сторе. Найди его название в существующем `auth.ts`.

**Step 3: В форме регистрации `src/pages/Login.tsx` передавать invite_code из URL**

Найти функцию `registerWithEmail` вызов в `Login.tsx` и добавить перед вызовом:

```typescript
const searchParams = new URLSearchParams(location.search);
const inviteCode = searchParams.get('invite') ?? undefined;
```

И передать в вызов:
```typescript
await registerWithEmail(email, password, firstName, inviteCode);
```

Также обновить сигнатуру `registerWithEmail` в сторе чтобы принимала `inviteCode`:
```typescript
registerWithEmail: async (email, password, firstName, inviteCode?) => {
  await authApi.registerEmailStandalone({
    email, password, first_name: firstName, invite_code: inviteCode
  });
  // ... остальная логика
}
```

**Step 4: Commit**

```bash
git add src/api/invite.ts src/store/auth.ts src/pages/Login.tsx
git commit -m "feat: add invite API client and store integration"
```

---

## Task 9: Frontend — роутинг

**Files:**
- Modify: `src/App.tsx`

**Step 1: Добавить Landing страницу в роутинг**

В `src/App.tsx`:

1. Импортировать Landing:
```typescript
import Landing from '@/pages/Landing';
```

2. Найти корневой роут (`path="/"` или `index`) и изменить его логику:

```tsx
// Вместо текущего корневого роута
{
  path: '/',
  element: <RootRedirect />,
}
```

Создать компонент `RootRedirect`:

```tsx
function RootRedirect() {
  const { isAuthenticated, user } = useAuthStore();

  // Забаненный или без инвайта — лендинг
  if (!isAuthenticated || !user?.invite_activated || user?.is_banned) {
    return <Landing />;
  }

  return <Navigate to="/dashboard" replace />;
}
```

> Изучи как сейчас устроен корневой роут в `App.tsx` — возможно там уже есть redirect логика, нужно её расширить а не заменить полностью.

**Step 2: Убедиться что `/register?invite=КОД` ведёт на Login с предзаполненным кодом**

Если отдельного роута `/register` нет — достаточно что `Login.tsx` читает `?invite=` из URL (сделано в Task 8).

Если нужен отдельный роут, добавить:
```tsx
{ path: '/register', element: <Login initialTab="register" /> }
```

**Step 3: Проверить в браузере**

1. Открыть `/` без JWT → должен показать лендинг
2. Залогиниться без инвайта → должен показать лендинг с полем промокода и кнопкой "Выйти"
3. Ввести валидный код → редирект в `/dashboard`
4. Забаненный юзер вводит код → "Аккаунт заблокирован"

**Step 4: Commit**

```bash
git add src/App.tsx
git commit -m "feat: add invite-based routing (landing vs dashboard)"
```

---

## Task 10: Деактивация при кике (истечение подписки)

**Files:**
- Modify: найти scheduler или webhook обработчик истечения подписки

**Step 1: Найти место где подписка помечается как expired**

```bash
grep -r "status.*expired\|EXPIRED\|subscription.*expire\|disable_user" \
  /home/krivonosov/projects/remnawave-bedolaga-telegram-bot/app --include="*.py" -l
```

**Step 2: Добавить вызов деактивации**

В найденном месте (там где подписка переходит в `expired` или `disabled`) добавить:

```python
from app.database.crud.invites import deactivate_user_invite

# После смены статуса подписки
# deactivate_user_invite уже проверяет is_permanent внутри
await deactivate_user_invite(db, user_id)
```

> Важно: `deactivate_user_invite` уже содержит проверку `if user and not user.is_permanent` — пользователи с бессрочной подпиской не будут деактивированы.

**Step 3: Commit**

```bash
git commit -m "feat: deactivate invite access on subscription expiry (skip permanent users)"
```

---

## Проверка всей системы

После выполнения всех тасков:

1. **Регистрация без кода:** `POST /cabinet/auth/email/register/standalone` → пользователь создан, `invite_activated=False`
2. **Регистрация с кодом:** тот же запрос с `invite_code` → `invite_activated=True`, инвайт помечен
3. **Активация кода:** `POST /cabinet/invite/activate` → работает для залогиненных незабаненных
4. **Активация забаненным:** → 403 "Аккаунт заблокирован"
5. **Генерация кода:** `POST /cabinet/invite/generate` → только для пользователей с `invite_activated=True` и `is_banned=False`
6. **Бессрочная подписка:** `POST /admin/users/{id}/set-permanent` → `is_permanent=True`, кик не срабатывает
7. **Бан:** `POST /admin/users/{id}/ban` → `is_banned=True`, `invite_activated=False`, подписки деактивированы
8. **Разбан:** `POST /admin/users/{id}/unban` → `is_banned=False`, но доступ не восстановлен (нужен новый инвайт)
9. **Фронтенд:** `/` без токена → лендинг, с токеном без кода → лендинг + промокод, с кодом → `/dashboard`
10. **Ссылка-инвайт:** `/register?invite=ABC123` → форма регистрации с предзаполненным кодом

---

## Дополнительно (не в скопе, но стоит иметь в виду)

- **Лимит генерации инвайтов на пользователя** — можно добавить позже
- **Страница "Мои инвайты" в ЛК** — список выданных кодов, кто использовал
- **Admin UI для бана/бессрочки** — кнопки в веб-админке (сейчас только API)
- **Telegram бот** — бот не нужен для работы системы
