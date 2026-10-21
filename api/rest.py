"""Веб-сервис (REST API) для SPA.

Домены:
  * услуга  — /api/receipt_categories...
  * пользователь — /api/users...

Устройство по методичке:
  * Handler  (этот файл)  — разбор HTTP-запроса, валидация, бизнес-правила;
  * Repository (db/repository.py) — все ORM-запросы к PostgreSQL;
  * сериализаторы (api/serializers.py) — формат JSON.

Правила:
  * адрес каждого метода начинается с /api, методы соответствуют REST;
  * записи в статусе «Удален» на клиент не передаются;
  * системные поля (ид, статус, создатель, даты) с клиента не принимаются —
    они вычисляются на бэкенде: пользователь берётся из cookie-сессии в Redis
    (core.auth / core.sessions), даты и статусы — из бизнес-логики;
  * без авторизации доступно только чтение (список, лента), методы
    создателя (добавление, публикация, удаление, лайк, черновик) возвращают
    401 Unauthorized — так же методы помечены в Swagger (cookie session_id);
  * в JSON нет ни статуса услуги, ни отдельных сообщений об ошибках —
    код состояния возвращает сам HTTP-ответ: 200, 201, 400, 401, 403, 404, 405, 409.
"""
from datetime import datetime

from fastapi import APIRouter, Body, Cookie, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.serializers import FeedOut, PublishIn, ReceiptOut, UserIn, UserOut
from core import sessions, storage
from core.auth import get_current_user, get_optional_user
from core.config import settings
from core.constants import (
    DEFAULT_CATEGORY,
    DEFAULT_CATEGORY_DISPLAY,
    DEFAULT_IMAGE_URL,
    DEFAULT_TYPE,
    DEFAULT_VIDEO_URL,
    STATUS_DELETED,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
)
from core.security import hash_password, verify_password
from db.repository import Repository
from db.session import get_db
from models.receipt_categories import Receipt_categories
from models.user import User

router = APIRouter(prefix="/api")

# описания ошибок для Swagger (тело ошибки пустое — код возвращает HTTP-ответ)
E400 = {"description": "Некорректные данные запроса"}
E401 = {"description": "Нет авторизации: отсутствует или истекла сессия"}
E403 = {"description": "Действие запрещено: услуга принадлежит другому пользователю"}
E403_PASSWORD = {"description": "Неверный пароль"}
E404 = {"description": "Запись не найдена"}
E409 = {"description": "Логин уже занят"}


# ---------------------------------------------------------------- dependencies

def get_repository(db: AsyncSession = Depends(get_db)) -> Repository:
    """Repository работает в той же сессии, что и текущий пользователь."""
    return Repository(db)


def _set_session_cookie(response: Response, session_id: str) -> None:
    """Куки с идентификатором сессии Redis: HttpOnly (JS недоступен), 24 часа."""
    response.set_cookie(
        key=settings.SESSION_COOKIE,
        value=session_id,
        max_age=settings.SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
    )


# ---------------------------------------------------------------- helpers

def _to_out(
    receipt: Receipt_categories,
    user: User | None,
    counts: dict[int, int],
    liked: set[int],
) -> ReceiptOut:
    """Сборка единого JSON-формата услуги (набор полей всегда одинаковый).

    Legacy-поля category, category_display, amount и date в ответ не входят:
    они остаются только в БД. user = None — гость: is_creator = 0, liked = 0.
    """
    return ReceiptOut(
        id_receipt_category=receipt.id_receipt_category,
        title=receipt.title or "",
        type=receipt.type,
        tax_code=receipt.tax_code,
        description=receipt.description,
        image_url=storage.public_url(receipt.image_url) or "",
        video_url=storage.public_url(receipt.video_url) or "",
        date_created=receipt.date_created,
        date_formed=receipt.date_formed,
        date_completed=receipt.date_completed,
        likes=counts.get(receipt.id_receipt_category, 0),
        is_creator=1 if user is not None and receipt.id_user == user.id_user else 0,
        liked=1 if receipt.id_receipt_category in liked else 0,
    )


async def _one_out(
    repo: Repository, user: User | None, receipt: Receipt_categories
) -> ReceiptOut:
    counts, liked = await repo.likes_meta(user.id_user if user else None, [receipt])
    return _to_out(receipt, user, counts, liked)


async def _many_out(
    repo: Repository, user: User | None, receipts: list[Receipt_categories]
) -> list[ReceiptOut]:
    counts, liked = await repo.likes_meta(user.id_user if user else None, receipts)
    return [_to_out(receipt, user, counts, liked) for receipt in receipts]


async def _save_upload(upload_file: UploadFile, kind: str) -> str | None:
    """Читает файл из запроса, генерирует латинское имя и кладёт его в MinIO."""
    data = await upload_file.read()
    if not data:
        return None
    name = storage.generate_name(
        upload_file.filename or "", upload_file.content_type or "", kind
    )
    storage.upload(data, name, upload_file.content_type or "")
    return name


# ---------------------------------------------------------------- домен «услуга»

@router.get(
    "/receipt_categories",
    response_model=list[ReceiptOut],
    tags=["Услуги"],
    summary="Список услуг",
    responses={401: E401},
)
async def list_receipt_categories(
    type: str | None = Query(None, description="income — поступление, expense — выплата"),
    tax_code: str | None = Query(None, description="код операции, например 01"),
    title: str | None = Query(None, description="поиск по названию (частичный, без учёта регистра)"),
    expense: bool | None = Query(None, description="true — только выплаты (type = expense)"),
    mine: bool | None = Query(None, description="true — только услуги текущего пользователя (нужна авторизация)"),
    repo: Repository = Depends(get_repository),
    user: User | None = Depends(get_optional_user),
):
    """Список опубликованных услуг с фильтрами."""
    if mine and user is None:
        raise HTTPException(status_code=401)

    receipts = await repo.list_receipts(
        type=type,
        tax_code=tax_code,
        title=title,
        expense=expense,
        mine=mine,
        user_id=user.id_user if user else None,
    )
    return await _many_out(repo, user, receipts)


@router.get(
    "/receipt_categories/feed",
    response_model=FeedOut,
    tags=["Услуги"],
    summary="Лента",
    responses={404: E404},
)
async def feed(
    id: int | None = Query(None, description="ид услуги из ленты; без параметра — первая опубликованная"),
    repo: Repository = Depends(get_repository),
    user: User | None = Depends(get_optional_user),
):
    """Опубликованная услуга ленты и данные следующей (ид и видео).

    В ответе у каждой услуги есть next_id_receipt_category и next_video_url:
    клиент показывает текущее видео и заранее подгружает следующее.
    После последней услуги лента начинается сначала (next — первая услуга).
    """
    if id is None:
        receipt = await repo.get_first_published()
    else:
        receipt = await repo.get_receipt(id)
        if receipt is not None and receipt.status != STATUS_PUBLISHED:
            raise HTTPException(status_code=404)
    if receipt is None:
        raise HTTPException(status_code=404)

    nxt = await repo.get_next_published(receipt.id_receipt_category)
    if nxt is None:  # конец ленты — начинаем сначала
        nxt = await repo.get_first_published()
    if nxt is None:
        raise HTTPException(status_code=404)

    out = await _one_out(repo, user, receipt)
    return FeedOut(
        **out.model_dump(),
        next_id_receipt_category=nxt.id_receipt_category,
        next_video_url=storage.public_url(nxt.video_url) or "",
    )


@router.get(
    "/receipt_categories/draft",
    response_model=ReceiptOut,
    tags=["Услуги"],
    summary="Черновик",
    responses={401: E401, 404: E404},
)
async def get_draft(
    repo: Repository = Depends(get_repository),
    user: User = Depends(get_current_user),
):
    """Черновик текущего пользователя."""
    receipt = await repo.get_draft(user.id_user)
    if receipt is None:
        raise HTTPException(status_code=404)
    return await _one_out(repo, user, receipt)


@router.post(
    "/receipt_categories",
    response_model=ReceiptOut,
    status_code=201,
    tags=["Услуги"],
    summary="Добавить услугу",
    responses={400: E400, 401: E401},
)
async def create_receipt_category(
    title: str = Form(..., max_length=100, description="название услуги"),
    type: str = Form(DEFAULT_TYPE, max_length=20, description="income — поступление, expense — выплата"),
    tax_code: str = Form("", max_length=20, description="код операции, например 01"),
    description: str = Form("", description="описание услуги"),
    image: UploadFile | None = File(None, description="файл изображения"),
    video: UploadFile | None = File(None, description="файл короткого видео"),
    repo: Repository = Depends(get_repository),
    user: User = Depends(get_current_user),
):
    """Добавление услуги с изображением и видео."""
    name = title.strip()
    if not name:
        raise HTTPException(status_code=400)

    receipt = await repo.get_draft(user.id_user)
    if receipt is None:
        receipt = Receipt_categories(
            status=STATUS_DRAFT,
            creator=user.username,
            id_user=user.id_user,
            date_created=datetime.now(),
            # legacy-колонки БД: в API и Swagger не показываются
            category=DEFAULT_CATEGORY,
            category_display=DEFAULT_CATEGORY_DISPLAY,
            image_url=DEFAULT_IMAGE_URL,
            video_url=DEFAULT_VIDEO_URL,
        )

    receipt.title = name
    receipt.type = type or DEFAULT_TYPE
    if tax_code.strip():
        receipt.tax_code = tax_code.strip()
    receipt.description = description.strip() or None

    if image is not None and image.filename:
        saved = await _save_upload(image, "image")
        if saved:
            receipt.image_url = saved
    if video is not None and video.filename:
        saved = await _save_upload(video, "video")
        if saved:
            receipt.video_url = saved

    await repo.save_receipt(receipt)
    return await _one_out(repo, user, receipt)


@router.put(
    "/receipt_categories/publish",
    response_model=ReceiptOut,
    tags=["Услуги"],
    summary="Опубликовать услугу",
    responses={400: E400, 401: E401, 404: E404},
)
async def publish_receipt_category(
    payload: PublishIn | None = Body(None),
    repo: Repository = Depends(get_repository),
    user: User = Depends(get_current_user),
):
    """Публикация черновика."""
    fields = payload.model_dump(exclude_unset=True) if payload else {}

    if fields.get("id_receipt_category") is not None:
        receipt = await repo.get_receipt(fields["id_receipt_category"])
        if receipt is None or receipt.id_user != user.id_user:
            raise HTTPException(status_code=404)
    else:
        receipt = await repo.get_draft(user.id_user)
        if receipt is None:
            raise HTTPException(status_code=404)

    if receipt.status != STATUS_DRAFT:
        raise HTTPException(status_code=404)

    if "type" in fields and fields["type"] is not None:
        if fields["type"] not in ("income", "expense"):
            raise HTTPException(status_code=400)
        receipt.type = fields["type"]
    if "tax_code" in fields:
        receipt.tax_code = (fields["tax_code"] or "").strip() or None
    if "description" in fields:
        receipt.description = fields["description"]

    receipt.status = STATUS_PUBLISHED
    receipt.date_formed = datetime.now()
    await repo.save_receipt(receipt)
    return await _one_out(repo, user, receipt)


@router.delete(
    "/receipt_categories/{receipt_category_id}",
    response_model=ReceiptOut,
    tags=["Услуги"],
    summary="Удалить услугу",
    responses={401: E401, 403: E403, 404: E404},
)
async def delete_receipt_category(
    receipt_category_id: int,
    repo: Repository = Depends(get_repository),
    user: User = Depends(get_current_user),
):
    """Мягкое удаление своей услуги."""
    receipt = await repo.get_receipt(receipt_category_id)
    if receipt is None or receipt.status == STATUS_DELETED:
        raise HTTPException(status_code=404)
    if receipt.id_user != user.id_user:
        raise HTTPException(status_code=403)

    receipt.status = STATUS_DELETED
    receipt.date_completed = datetime.now()
    await repo.save_receipt(receipt)
    return await _one_out(repo, user, receipt)


@router.post(
    "/receipt_categories/{receipt_category_id}/like",
    response_model=ReceiptOut,
    tags=["Услуги"],
    summary="Лайк",
    responses={400: E400, 401: E401, 404: E404},
)
async def like_receipt_category(
    receipt_category_id: int,
    payload: dict | None = Body(None, description='{"value": 1} — поставить лайк, {"value": 0} — снять'),
    value: int | None = Query(None, description="0 — снять лайк, 1 — поставить"),
    repo: Repository = Depends(get_repository),
    user: User = Depends(get_current_user),
):
    """Поставить или снять лайк."""
    receipt = await repo.get_receipt(receipt_category_id)
    if receipt is None or receipt.status != STATUS_PUBLISHED:
        raise HTTPException(status_code=404)

    raw = value
    if raw is None and payload:
        for key in ("value", "like", "liked"):
            if key in payload:
                raw = payload[key]
                break
    if raw is None:
        raw = 1

    try:
        flag = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400)
    if flag not in (0, 1):
        raise HTTPException(status_code=400)

    await repo.set_like(user.id_user, receipt.id_receipt_category, flag)
    return await _one_out(repo, user, receipt)


# ---------------------------------------------------------------- домен «пользователь»

@router.post(
    "/users/register",
    response_model=UserOut,
    status_code=201,
    tags=["Пользователи"],
    summary="Регистрация",
    responses={400: E400, 409: E409},
)
async def register_user(
    payload: UserIn,
    response: Response,
    repo: Repository = Depends(get_repository),
):
    """Регистрация пользователя и автоматический вход."""
    if await repo.get_user_by_login(payload.username) is not None:
        raise HTTPException(status_code=409)

    try:
        user = await repo.create_user(payload.username, hash_password(payload.password))
    except IntegrityError:
        # гонка двух одновременных регистраций с одинаковым логином
        await repo.db.rollback()
        raise HTTPException(status_code=409)

    session_id = await sessions.create_session(user.id_user, user.username)
    _set_session_cookie(response, session_id)
    return UserOut(id_user=user.id_user, username=user.username)


@router.post(
    "/users/login",
    response_model=UserOut,
    tags=["Пользователи"],
    summary="Вход",
    responses={400: E400, 403: E403_PASSWORD, 404: E404},
)
async def login_user(
    payload: UserIn,
    response: Response,
    repo: Repository = Depends(get_repository),
):
    """Проверка логина и пароля, создание сессии."""
    user = await repo.get_user_by_login(payload.username)
    if user is None:
        raise HTTPException(status_code=404)

    is_valid, needs_rehash = verify_password(payload.password, user.password)
    if not is_valid:
        raise HTTPException(status_code=403)
    if needs_rehash:
        user.password = hash_password(payload.password)
        await repo.save_user(user)

    session_id = await sessions.create_session(user.id_user, user.username)
    _set_session_cookie(response, session_id)
    return UserOut(id_user=user.id_user, username=user.username)


@router.post(
    "/users/logout",
    tags=["Пользователи"],
    summary="Выход",
)
async def logout_user(
    response: Response,
    session_id: str | None = Cookie(None, alias=settings.SESSION_COOKIE),
):
    """Выход из системы.

    С указанной сессией (cookie session_id) — завершается только она.
    Без сессии (пусто) — завершаются все сессии всех пользователей.
    """
    if session_id:
        await sessions.delete_session(session_id)
    else:
        await sessions.delete_all_sessions()
    response.delete_cookie(settings.SESSION_COOKIE)
    return {}

