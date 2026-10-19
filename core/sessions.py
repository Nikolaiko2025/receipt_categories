"""Сессии в Redis (методичка: хранение сессий + куки).

Сессия — пара «ключ ↔ пользователь» в Redis:
    ключ   session:<идентификатор.cookie>   (например session:3f2b...a91)
    значение  "<id_user>|<username>"          — кого показать в Redis через cmd
    TTL    settings.SESSION_TTL_SECONDS      — само вычищается после простоя

Идентификатор сессии (случайный uuid4) сервер возвращает клиенту в cookie
session_id (HttpOnly) методами /api/users/login и /api/users/register;
на каждом запросе идентификатор читается из cookie и по нему из Redis
восстанавливается пользователь (см. core.auth). Logout удаляет ключ из Redis
и cookie из ответа. Сам клиент идентификатор сессии не придумывает и не
подделывает: в Redis лежит только серверная половина данных.
"""
import uuid

import redis.asyncio as aioredis

from core.config import settings

# один клиент Redis на приложение (соединение открывается лениво, при первом запросе)
_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

SESSION_PREFIX = "session:"


def _key(session_id: str) -> str:
    return f"{SESSION_PREFIX}{session_id}"


async def create_session(user_id: int, username: str) -> str:
    """Создаёт сессию: возвращает новый идентификатор, значение кладётся в Redis с TTL."""
    session_id = uuid.uuid4().hex
    await _client.set(_key(session_id), f"{user_id}|{username}", ex=settings.SESSION_TTL_SECONDS)
    return session_id


async def get_session_user_id(session_id: str | None) -> int | None:
    """id_user по идентификатору сессии; None — сессии нет (или истёк TTL)."""
    if not session_id:
        return None
    raw = await _client.get(_key(session_id))
    if not raw:
        return None
    try:
        return int(raw.split("|", 1)[0])
    except ValueError:
        return None


async def delete_session(session_id: str | None) -> None:
    """Удаляет сессию из Redis (метод logout); неизвестный идентификатор — не ошибка."""
    if session_id:
        await _client.delete(_key(session_id))
