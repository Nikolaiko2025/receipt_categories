"""Аутентификация и авторизация веб-сервиса: сессии в Redis + cookie.

Аутентификация (проверка логина/пароля) — методы домена «пользователь»
/api/users/register и /api/users/login: после проверки учётных данных сервер
создаёт сессию в Redis (core.sessions) и возвращает её идентификатор в
cookie session_id (HttpOnly). Деавторизация — /api/users/logout: сессия
удаляется из Redis, cookie — из ответа.

Авторизация (кто зван работать с методом) — на каждом запросе:
  * get_optional_user — чтение (список услуг, лента): без cookie или с
    истёкшей сессией работает гость (user = None), данные отдаются,
    is_creator = 0, лайки гостя не сохраняются;
  * get_current_user — методы создателя (добавление, публикация, удаление,
    лайк, черновик): нет валидной сессии -> 401 Unauthorized.

APIKeyCookie (auto_error=False) — только документ: описывает cookie как
схему безопасности в Swagger, поэтому у методов создателя появляется кнопка
Authorize, а чтение остаётся открытым. Проверку ведёт сам get_current_user.
"""
from fastapi import Cookie, Depends, HTTPException
from fastapi.security import APIKeyCookie
from sqlalchemy.ext.asyncio import AsyncSession

from core import sessions
from core.config import settings
from db.repository import Repository
from db.session import get_db
from models.user import User

# схема безопасности для OpenAPI/Swagger: cookie session_id (без авто-ошибки,
# реальную проверку ведёт get_current_user)
cookie_security = APIKeyCookie(
    name=settings.SESSION_COOKIE,
    description=(
        "Идентификатор сессии в Redis. Выдаётся cookie в ответах "
        "POST /api/users/register и POST /api/users/login (HttpOnly, 24 часа). "
        "Авторизуйтесь этим значением в Swagger или передайте как cookie "
        "session_id в заголовке Cookie из Postman/Insomnia."
    ),
    auto_error=False,
)


async def get_optional_user(
    session_id: str | None = Cookie(None, alias=settings.SESSION_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Текущий пользователь по cookie-сессии; None — гость (чтение без авторизации)."""
    user_id = await sessions.get_session_user_id(session_id)
    if user_id is None:
        return None
    return await Repository(db).get_user_by_id(user_id)


async def get_current_user(
    session_id: str | None = Depends(cookie_security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Текущий пользователь для методов создателя: нет валидной сессии -> 401."""
    user_id = await sessions.get_session_user_id(session_id)
    if user_id is None:
        raise HTTPException(status_code=401)
    user = await Repository(db).get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401)
    return user
