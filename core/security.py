"""Хеширование и проверка паролей пользователей.

Новые пароли хешируются bcrypt (cost factor 12). Формат хеша:
    $2b$12$<salt+hash>

Поддерживаются старые записи:
  * pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex> — предыдущая версия;
  * пароль открытым текстом — legacy-записи до добавления хеширования.

После успешного входа старый пароль автоматически перезаписывается bcrypt-
хешем (ленивая миграция). Ограничение bcrypt — не более 72 байт пароля;
длина проверяется и в Pydantic-схеме UserIn.
"""
import hashlib
import hmac

import bcrypt

BCRYPT_ROUNDS = 12
MAX_PASSWORD_BYTES = 72
PBKDF2_ALGORITHM = "pbkdf2_sha256"


def _password_bytes(password: str) -> bytes:
    """Пароль в UTF-8 с проверкой ограничения bcrypt (72 байта)."""
    raw = password.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        raise ValueError("пароль не должен превышать 72 байта")
    return raw


def hash_password(password: str) -> str:
    """Возвращает bcrypt-хеш пароля с случайной солью (cost factor 12)."""
    return bcrypt.hashpw(
        _password_bytes(password),
        bcrypt.gensalt(rounds=BCRYPT_ROUNDS),
    ).decode("ascii")


def _is_bcrypt(stored: str) -> bool:
    return stored.startswith(("$2a$", "$2b$", "$2y$"))


def _verify_pbkdf2(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, expected = stored.split("$", 3)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        )
        return hmac.compare_digest(
            digest.hex().encode("ascii"), expected.encode("ascii")
        )
    except (TypeError, ValueError):
        return False


def verify_password(password: str, stored: str) -> tuple[bool, bool]:
    """Проверяет пароль.

    Возвращает пару (пароль верный, нужно ли перехешировать).
    Для bcrypt второе значение False; для PBKDF2 и открытого текста True —
    после успешного входа такой пароль нужно заменить на hash_password(password).
    """
    if not stored:
        return False, False

    if _is_bcrypt(stored):
        try:
            raw = password.encode("utf-8")
            if len(raw) > MAX_PASSWORD_BYTES:
                return False, False
            return bcrypt.checkpw(raw, stored.encode("ascii")), False
        except (TypeError, ValueError):
            return False, False

    if stored.startswith(f"{PBKDF2_ALGORITHM}$"):
        return _verify_pbkdf2(password, stored), True

    # legacy-запись: пароль лежит открытым текстом
    valid = hmac.compare_digest(
        password.encode("utf-8"), stored.encode("utf-8")
    )
    return valid, valid
