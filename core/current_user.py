"""Функция-синглтон: текущий (зафиксированный) пользователь.

Авторизацию делаем в 4-й лабораторной, поэтому во всех методах веб-сервиса
пользователь-создатель задан константой CURRENT_USER_LOGIN и возвращается
функцией-синглтоном: объект User создаётся один раз при первом обращении и
дальше переиспользуется всеми запросами.

Системные поля услуги (создатель, статус, даты) берутся отсюда и с клиента
не принимаются.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User

# константа: пользователь, от имени которого работают все методы API
CURRENT_USER_LOGIN = "test_user"
CURRENT_USER_PASSWORD = "test1_1"

_current_user: User | None = None


async def get_current_user(db: AsyncSession) -> User:
    """Синглтон: возвращает закешированного пользователя (создаёт при необходимости)."""
    global _current_user

    if _current_user is None:
        result = await db.execute(
            select(User).where(User.username == CURRENT_USER_LOGIN)
        )
        user = result.scalar_one_or_none()

        if user is None:
            user = User(username=CURRENT_USER_LOGIN, password=CURRENT_USER_PASSWORD)
            db.add(user)
            await db.commit()
            await db.refresh(user)

        _current_user = user

    return _current_user
