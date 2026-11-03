from fastapi import Cookie, Depends, HTTPException
from fastapi.security import APIKeyCookie
from sqlalchemy.ext.asyncio import AsyncSession

from core import sessions
from core.config import settings
from db.repository import Repository
from db.session import get_db
from models.user import User


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
