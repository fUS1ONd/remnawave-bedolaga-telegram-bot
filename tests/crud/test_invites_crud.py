"""Тесты для CRUD-операций инвайт-кодов."""

import string
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.database.crud.invites import (
    _generate_code,
    activate_invite,
    ban_user,
    create_invite,
    deactivate_user_invite,
    get_all_invites,
    get_invite,
    get_user_invites,
    set_permanent,
    unban_user,
)


def test_generate_code_default_length():
    """Генерируемый код должен иметь длину 10 символов по умолчанию."""
    code = _generate_code()
    assert len(code) == 10


def test_generate_code_custom_length():
    """Генерируемый код должен иметь заданную длину."""
    code = _generate_code(length=16)
    assert len(code) == 16


def test_generate_code_valid_characters():
    """Код должен состоять только из заглавных букв и цифр."""
    valid_chars = set(string.ascii_uppercase + string.digits)
    code = _generate_code(length=100)
    assert all(c in valid_chars for c in code)


def test_generate_code_uniqueness():
    """Два сгенерированных кода не должны совпадать (статистически)."""
    codes = {_generate_code() for _ in range(100)}
    assert len(codes) == 100


async def test_get_invite_found():
    """Получение существующего инвайта по коду."""
    mock_invite = MagicMock()
    mock_invite.code = 'TESTCODE12'

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_invite

    db = AsyncMock()
    db.execute.return_value = mock_result

    result = await get_invite(db, 'TESTCODE12')
    assert result == mock_invite


async def test_get_invite_not_found():
    """Получение несуществующего инвайта возвращает None."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute.return_value = mock_result

    result = await get_invite(db, 'NOEXIST123')
    assert result is None


async def test_activate_invite_not_found():
    """Активация несуществующего инвайта возвращает ошибку."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute.return_value = mock_result

    success, msg = await activate_invite(db, 'BADCODE123', user_id=1)
    assert success is False
    assert 'не найден' in msg


async def test_activate_invite_already_used():
    """Активация уже использованного инвайта возвращает ошибку."""
    mock_invite = MagicMock()
    mock_invite.code = 'USEDCODE12'
    mock_invite.used_by = 42  # уже использован

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_invite

    db = AsyncMock()
    db.execute.return_value = mock_result

    success, msg = await activate_invite(db, 'USEDCODE12', user_id=1)
    assert success is False
    assert 'уже использован' in msg


async def test_activate_invite_user_banned():
    """Активация инвайта заблокированным пользователем возвращает ошибку."""
    mock_invite = MagicMock()
    mock_invite.code = 'GOODCODE12'
    mock_invite.used_by = None

    mock_user = MagicMock()
    mock_user.is_banned = True

    # Первый вызов execute — для инвайта, второй — для пользователя
    mock_result_invite = MagicMock()
    mock_result_invite.scalar_one_or_none.return_value = mock_invite

    mock_result_user = MagicMock()
    mock_result_user.scalar_one_or_none.return_value = mock_user

    db = AsyncMock()
    db.execute.side_effect = [mock_result_invite, mock_result_user]

    success, msg = await activate_invite(db, 'GOODCODE12', user_id=1)
    assert success is False
    assert 'заблокирован' in msg


async def test_activate_invite_success():
    """Успешная активация инвайта."""
    mock_invite = MagicMock()
    mock_invite.code = 'GOODCODE12'
    mock_invite.used_by = None

    mock_user = MagicMock()
    mock_user.is_banned = False

    mock_result_invite = MagicMock()
    mock_result_invite.scalar_one_or_none.return_value = mock_invite

    mock_result_user = MagicMock()
    mock_result_user.scalar_one_or_none.return_value = mock_user

    db = AsyncMock()
    db.execute.side_effect = [mock_result_invite, mock_result_user]

    success, msg = await activate_invite(db, 'GOODCODE12', user_id=1)
    assert success is True
    assert 'успешно' in msg
    assert mock_invite.used_by == 1
    assert mock_user.invite_activated is True
    db.commit.assert_awaited_once()


async def test_get_user_invites():
    """Получение списка инвайтов пользователя."""
    mock_invites = [MagicMock(), MagicMock()]

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = mock_invites

    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    db = AsyncMock()
    db.execute.return_value = mock_result

    result = await get_user_invites(db, user_id=1)
    assert len(result) == 2


async def test_get_all_invites():
    """Получение всех инвайтов."""
    mock_invites = [MagicMock(), MagicMock(), MagicMock()]

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = mock_invites

    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    db = AsyncMock()
    db.execute.return_value = mock_result

    result = await get_all_invites(db)
    assert len(result) == 3


async def test_deactivate_user_invite_permanent_skipped():
    """Деактивация пропускается для пользователя с бессрочной подпиской."""
    mock_user = MagicMock()
    mock_user.is_permanent = True
    mock_user.invite_activated = True

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user

    db = AsyncMock()
    db.execute.return_value = mock_result

    await deactivate_user_invite(db, user_id=1)
    # invite_activated не должен измениться
    assert mock_user.invite_activated is True
    db.commit.assert_not_awaited()


async def test_deactivate_user_invite_success():
    """Деактивация подписки обычного пользователя."""
    mock_user = MagicMock()
    mock_user.is_permanent = False

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user

    db = AsyncMock()
    db.execute.return_value = mock_result

    await deactivate_user_invite(db, user_id=1)
    assert mock_user.invite_activated is False
    db.commit.assert_awaited_once()


async def test_ban_user():
    """Блокировка пользователя устанавливает is_banned и снимает invite_activated."""
    mock_user = MagicMock()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user

    db = AsyncMock()
    db.execute.return_value = mock_result

    await ban_user(db, user_id=1)
    assert mock_user.is_banned is True
    assert mock_user.invite_activated is False
    db.commit.assert_awaited_once()


async def test_unban_user():
    """Разблокировка пользователя снимает is_banned, подписки не восстанавливаются."""
    mock_user = MagicMock()
    mock_user.invite_activated = False

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user

    db = AsyncMock()
    db.execute.return_value = mock_result

    await unban_user(db, user_id=1)
    assert mock_user.is_banned is False
    # invite_activated НЕ восстанавливается
    assert mock_user.invite_activated is False
    db.commit.assert_awaited_once()


async def test_set_permanent_true():
    """Установка бессрочной подписки."""
    mock_user = MagicMock()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user

    db = AsyncMock()
    db.execute.return_value = mock_result

    await set_permanent(db, user_id=1, value=True)
    assert mock_user.is_permanent is True
    db.commit.assert_awaited_once()


async def test_set_permanent_false():
    """Снятие бессрочной подписки."""
    mock_user = MagicMock()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user

    db = AsyncMock()
    db.execute.return_value = mock_result

    await set_permanent(db, user_id=1, value=False)
    assert mock_user.is_permanent is False
    db.commit.assert_awaited_once()
