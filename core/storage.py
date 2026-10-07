"""Файлы услуг в MinIO: изображение и короткое видео.

В БД сохраняется только сгенерированное латинское имя файла
(например 8f3c2a1d9b7e4c06a1d5f2e7b3c91a44.jpg), сами файлы лежат в бакете
MinIO. Публичный URL для клиента собирается из настроек MinIO.
"""
import io
import re
import uuid

from minio import Minio

from core.config import settings

_client: Minio | None = None
_bucket_ready = False

_IMAGE_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
_VIDEO_EXTENSIONS = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}


def _get_client() -> Minio:
    """Соединение с MinIO (создаётся один раз — тоже синглтон)."""
    global _client
    if _client is None:
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
    return _client


def ensure_bucket() -> None:
    """Создаёт бакет, если его ещё нет (вызывается перед загрузкой файла)."""
    global _bucket_ready
    if _bucket_ready:
        return
    client = _get_client()
    if not client.bucket_exists(settings.MINIO_BUCKET):
        client.make_bucket(settings.MINIO_BUCKET)
    _bucket_ready = True


def generate_name(original_name: str, content_type: str, kind: str) -> str:
    """Генерирует имя файла из латиницы и цифр: <uuid>.<расширение>."""
    extension = _extension(original_name)
    if not extension:
        extension = _IMAGE_EXTENSIONS.get(content_type) if kind == "image" else _VIDEO_EXTENSIONS.get(content_type)
    if not extension:
        extension = ".jpg" if kind == "image" else ".mp4"
    return f"{uuid.uuid4().hex}{extension}"


def upload(data: bytes, name: str, content_type: str) -> str:
    """Кладёт файл в MinIO и возвращает его имя (то, что хранится в БД)."""
    ensure_bucket()
    _get_client().put_object(
        settings.MINIO_BUCKET,
        name,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type or "application/octet-stream",
    )
    return name


def public_url(stored: str | None) -> str | None:
    """Из значения поля image_url/video_url собирает URL для клиента.

    Старые записи хранят полный URL или путь до статики — они возвращаются
    как есть, новые (только имя файла) дополняются адресом MinIO.
    """
    if not stored:
        return stored
    if stored.startswith(("http://", "https://", "/", "#")):
        return stored
    return f"{settings.MINIO_PUBLIC_URL}/{settings.MINIO_BUCKET}/{stored}"


def _extension(original_name: str) -> str:
    """Расширение исходного файла, приведённое к латинице."""
    if "." not in original_name:
        return ""
    extension = original_name.rsplit(".", 1)[-1].lower()
    extension = re.sub(r"[^a-z0-9]", "", extension)
    return f".{extension}" if extension else ""
