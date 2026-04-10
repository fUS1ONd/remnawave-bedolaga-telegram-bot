# Система инвайтов для bedolaga

## Концепция

Сайт выглядит как обычный лендинг (фейковый магазин диванов). Личный кабинет VPN-сервиса скрыт за инвайт-кодом. Только пользователи с активированным кодом видят настоящий ЛК.

---

## Состояния пользователя

| Состояние | Что видит |
|---|---|
| Не залогинен | Диванный лендинг + кнопка "Войти" |
| Залогинен, без кода | Диванный лендинг + кнопка "Выйти" + поле промокода внизу |
| Залогинен, код активирован | Редирект в полный ЛК (`/dashboard`) |
| Залогинен, забанен | Диванный лендинг + поле промокода (но активация отклоняется: "Аккаунт заблокирован") |

---

## Роутинг (bedolaga-cabinet)

```
/ (корень)
  ├── Нет JWT → диванный лендинг
  ├── JWT + is_banned = true → диванный лендинг (промокод не сработает)
  ├── JWT + invite_activated = false → диванный лендинг (с "Выйти" и промокодом)
  └── JWT + invite_activated = true → редирект на /dashboard

/register?invite=КОД
  → форма регистрации с предзаполненным кодом
  → после регистрации с валидным кодом → редирект в /dashboard
```

---

## База данных

### Новая таблица `invites`

```sql
CREATE TABLE invites (
    code        VARCHAR(16) PRIMARY KEY,
    created_by  INTEGER NOT NULL REFERENCES users(id),
    used_by     INTEGER REFERENCES users(id),
    used_at     TIMESTAMP,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);
```

- Код одноразовый, бессрочный
- После использования повторная активация невозможна
- При кике (истекла подписка) → `invite_activated = FALSE` на пользователе, но запись в `invites` остаётся (история сохраняется)
- Для возврата нужен новый код от кого-то из пользователей

### Изменения таблицы `users`

```sql
ALTER TABLE users ADD COLUMN invite_activated BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN is_permanent BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN is_banned BOOLEAN NOT NULL DEFAULT FALSE;
```

---

## Флаги пользователя

### `is_permanent` — бессрочная подписка

- Бесконечный доступ к VPN, не кикается за неоплату
- Назначается/снимается админом через веб-админку
- Для родных и близких друзей

### `is_banned` — бан

- Полная блокировка: VPN отключен, доступ к ЛК закрыт
- При бане: `is_banned = true`, `invite_activated = false`, все подписки деактивируются
- При разбане: только `is_banned = false` — доступ НЕ восстанавливается, нужен новый инвайт
- Забаненный не может активировать инвайт-код

### Приоритет флагов

| `is_permanent` | `is_banned` | Результат |
|---|---|---|
| false | false | Обычный пользователь, подчиняется сроку подписки |
| true | false | Бессрочная подписка, кик по истечению не срабатывает |
| любое | true | Заблокирован: нет доступа к ЛК, VPN отключен |

---

## Backend API

### Для пользователей

```
POST /cabinet/invite/activate
Body: { code: "ABC123XY" }
Auth: JWT

→ Проверяет: не забанен, код существует, не использован
→ Порядок проверок:
  1. is_banned? → "Аккаунт заблокирован"
  2. invite_activated? → "Доступ уже активирован"
  3. Код валиден и не использован? → активируем
→ Ставит used_by + used_at на инвайте
→ Ставит invite_activated = TRUE на пользователе
→ { success: true }
```

```
GET /cabinet/invite/my
Auth: JWT

→ Список инвайтов созданных текущим пользователем
→ [{ code, used_by_username, used_at, created_at }]
```

```
POST /cabinet/invite/generate
Auth: JWT + invite_activated = TRUE + не забанен

→ Генерирует новый код для текущего пользователя
→ { code: "ABC123XY" }
```

### Для администратора

```
GET  /admin/invites
POST /admin/invites/generate?user_id=...
DELETE /admin/invites/{code}

POST /admin/users/{user_id}/set-permanent
Body: { "value": true/false }
→ Устанавливает/снимает бессрочную подписку

POST /admin/users/{user_id}/ban
→ is_banned = true, invite_activated = false, деактивация всех VPN-подписок

POST /admin/users/{user_id}/unban
→ is_banned = false (подписки и invite_activated НЕ восстанавливаются)
```

### Изменение в регистрации

`POST /cabinet/auth/email/register/standalone` — добавляется опциональный параметр `invite_code`.

Если передан и валиден → сразу `invite_activated = TRUE`, редирект в ЛК без дополнительного шага.

---

## Frontend (bedolaga-cabinet)

### Диванный лендинг

- Готовый HTML-шаблон мебельного магазина
- В футере или шапке скромная кнопка/ссылка "Войти"
- Если пользователь залогинен без кода: кнопка "Выйти" в углу
- Внизу страницы (только для залогиненных без кода):

```
Промокод
[          ] [→]
```

- Забаненный видит то же самое, но при вводе кода получает "Аккаунт заблокирован"

### Форма регистрации

- Поле `invite_code` скрыто, заполняется из `?invite=КОД` в URL
- Если параметра нет — поле отсутствует, регистрация создаёт аккаунт без кода
- После успешной регистрации с кодом → `/dashboard`
- После регистрации без кода → остаётся на лендинге (с полем промокода)

---

## Генерация инвайтов

Любой пользователь с `invite_activated = TRUE` может генерировать коды через ЛК.

Цепочка: Ты (супер-админ) → выдаёшь код → пользователь A активирует → пользователь A генерирует код → пользователь B активирует → и так далее.

Ограничения на кол-во генерируемых кодов — на усмотрение (можно добавить лимит позже).

---

## Проверки доступа (middleware)

Для всех эндпоинтов ЛК (`/cabinet/*` кроме auth) — dependency `get_current_active_user`:
1. Проверяет JWT
2. Проверяет `is_banned = false`
3. Если забанен → 403 "Аккаунт заблокирован"

Для кика по истечению подписки:
1. Проверяет `is_permanent` — если true, пропускаем
2. Иначе деактивируем: `invite_activated = false`

---

## Файлы которые затрагиваются

### Backend (`remnawave-bedolaga-telegram-bot`)
- `app/database/models.py` — новая модель `Invite`, поля `invite_activated`, `is_permanent`, `is_banned` в `User`
- `app/cabinet/routes/auth.py` — проверка `invite_code` при регистрации
- `app/cabinet/routes/invite.py` — новый файл с эндпоинтами инвайтов
- `app/cabinet/routes/admin_invites.py` — новый файл для admin API (инвайты + бан + бессрочка)
- `app/webapi/dependencies.py` — dependency `get_current_active_user` с проверкой бана
- `migrations/alembic/versions/XXXX_add_invites.py` — новая миграция

### Frontend (`bedolaga-cabinet`)
- `src/pages/Landing.tsx` — новый компонент диванного лендинга
- `src/pages/Login.tsx` — добавить поле `invite_code` из URL параметра
- `src/api/invite.ts` — новый API клиент
- `src/store/auth.ts` — логика `invite_activated`, обработка бана в стейте
- `src/router.tsx` — логика редиректа по `invite_activated` и `is_banned`
