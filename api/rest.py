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
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Body, Cookie, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api.serializers import PublishIn, ReceiptOut, UserIn, UserOut
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
from db.repository import Repository
from db.session import get_db
from models.receipt_categories import Receipt_categories
from models.user import User

router = APIRouter(prefix="/api", tags=["Услуги"])


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

    category, category_display и date в ответ не входят — это legacy-поля
    прежней версии схемы, в интерфейсе их заменяют type и tax_code.
    user = None — гость: is_creator = 0, liked = 0.
    """
    return ReceiptOut(
        id_receipt_category=receipt.id_receipt_category,
        title=receipt.title or "",
        type=receipt.type,
        tax_code=receipt.tax_code,
        amount=float(receipt.amount) if receipt.amount is not None else None,
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


def _parse_amount(raw: str | None) -> Decimal | None:
    """1200000 | 1 234,56 -> Decimal; пусто -> None; мусор -> 400 Bad Request."""
    if raw is None or not raw.strip():
        return None
    cleaned = raw.strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise HTTPException(status_code=400)


def _parse_date(raw: str | None) -> date | None:
    """2026-10-07 | 07.10.2026 | 2026-10-07T12:00 -> date; пусто -> None; мусор -> 400."""
    if raw is None or not raw.strip():
        return None
    value = raw.strip()
    for parser in (
        lambda v: datetime.fromisoformat(v).date(),
        lambda v: datetime.strptime(v, "%d.%m.%Y").date(),
        lambda v: datetime.strptime(v, "%Y/%m/%d").date(),
    ):
        try:
            return parser(value)
        except ValueError:
            continue
    raise HTTPException(status_code=400)


# ---------------------------------------------------------------- домен «услуга»

@router.get("/receipt_categories", response_model=list[ReceiptOut])
async def list_receipt_categories(
    type: str | None = Query(None, description="income — поступление, expense — выплата"),
    category: str | None = Query(None, description="код категории: debit, sales, credit, salary, suppliers"),
    title: str | None = Query(None, description="поиск по названию (частичный, без учёта регистра)"),
    min_amount: float | None = Query(None, description="сумма от"),
    max_amount: float | None = Query(None, description="сумма до"),
    date_from: date | None = Query(None, description="дата операции от (ГГГГ-ММ-ДД)"),
    date_to: date | None = Query(None, description="дата операции до (ГГГГ-ММ-ДД)"),
    expense: bool | None = Query(None, description="true — только выплаты (type = expense)"),
    mine: bool | None = Query(None, description="true — только услуги текущего пользователя (нужна авторизация)"),
    repo: Repository = Depends(get_repository),
    user: User | None = Depends(get_optional_user),
):
    """Список опубликованных услуг с фильтрацией на стороне БД.

    Метод чтения: работает и без авторизации (тогда user — гость, is_creator = 0).
    Признак is_creator = 1, если создатель услуги совпадает с текущим
    пользователем. Фильтр mine=true относится к личным данным — без
    авторизации возвращает 401 Unauthorized.
    """
    if mine and user is None:
        raise HTTPException(status_code=401)

    receipts = await repo.list_receipts(
        type=type,
        category=category,
        title=title,
        min_amount=min_amount,
        max_amount=max_amount,
        date_from=date_from,
        date_to=date_to,
        expense=expense,
        mine=mine,
        user_id=user.id_user if user else None,
    )
    return await _many_out(repo, user, receipts)


@router.get("/receipt_categories/feed", response_model=ReceiptOut)
async def feed(
    repo: Repository = Depends(get_repository),
    user: User | None = Depends(get_optional_user),
):
    """Лента без указания ид: первая опубликованная услуга (LIMIT 1).

    Метод чтения — доступен без авторизации (гость: is_creator = 0, liked = 0).
    """
    receipt = await repo.get_first_published()
    if receipt is None:
        raise HTTPException(status_code=404)
    return await _one_out(repo, user, receipt)


@router.get("/receipt_categories/feed/{receipt_category_id}", response_model=ReceiptOut)
async def feed_by_id(
    receipt_category_id: int,
    next: bool = Query(False, description="true — следующая опубликованная услуга"),
    repo: Repository = Depends(get_repository),
    user: User | None = Depends(get_optional_user),
):
    """Лента по ид. next=true — следующая опубликованная услуга (LIMIT 1);
    несуществующий ид — 404, конец ленты — начинаем сначала.

    Метод чтения — доступен без авторизации (гость: is_creator = 0, liked = 0).
    """
    current = await repo.get_receipt(receipt_category_id)
    if current is None or current.status != STATUS_PUBLISHED:
        raise HTTPException(status_code=404)

    if not next:
        return await _one_out(repo, user, current)

    receipt = await repo.get_next_published(receipt_category_id)
    if receipt is None:  # конец ленты — начинаем сначала
        receipt = await repo.get_first_published()
    if receipt is None:
        raise HTTPException(status_code=404)
    return await _one_out(repo, user, receipt)


@router.get("/receipt_categories/draft", response_model=ReceiptOut)
async def get_draft(
    repo: Repository = Depends(get_repository),
    user: User = Depends(get_current_user),
):
    """Поля черновика: ид не указывается, запись не более 1 на пользователя.

    Личные данные — нужна авторизация (cookie session_id), иначе 401.
    """
    receipt = await repo.get_draft(user.id_user)
    if receipt is None:
        raise HTTPException(status_code=404)
    return await _one_out(repo, user, receipt)


@router.post("/receipt_categories", response_model=ReceiptOut, status_code=201)
async def create_receipt_category(
    title: str = Form(..., max_length=100, description="название услуги"),
    type: str = Form(DEFAULT_TYPE, max_length=20, description="income — поступление, expense — выплата"),
    tax_code: str = Form("", max_length=20, description="код операции, например 01"),
    category: str = Form(DEFAULT_CATEGORY, max_length=20),
    category_display: str = Form(DEFAULT_CATEGORY_DISPLAY, max_length=50),
    amount: str = Form("", description="сумма: 1200000 или 1 234,56"),
    date_value: str = Form("", alias="date", description="дата: ГГГГ-ММ-ДД или ДД.ММ.ГГГГ"),
    description: str = Form(""),
    image: UploadFile | None = File(None, description="файл изображения"),
    video: UploadFile | None = File(None, description="файл короткого видео"),
    repo: Repository = Depends(get_repository),
    user: User = Depends(get_current_user),
):
    """Добавление услуги (multipart/form-data): файлы image и video уходят в MinIO,
    в БД сохраняются их сгенерированные латинские имена.

    Метод создателя — нужна авторизация (cookie session_id), иначе 401.
    Создатель услуги (creator, id_user) берётся из сессии, с клиента не
    принимается. Создаётся не более одного черновика на пользователя: если
    черновик уже есть, обновляется он. Некорректные сумма/дата -> 400 Bad
    Request (до загрузки файлов).
    """
    name = title.strip()
    amount_value = _parse_amount(amount)      # 400 при мусоре
    date_value_parsed = _parse_date(date_value)  # 400 при мусоре
    if not name:
        raise HTTPException(status_code=400)

    receipt = await repo.get_draft(user.id_user)
    if receipt is None:
        receipt = Receipt_categories(
            status=STATUS_DRAFT,
            creator=user.username,
            id_user=user.id_user,
            date_created=datetime.now(),
            image_url=DEFAULT_IMAGE_URL,
            video_url=DEFAULT_VIDEO_URL,
        )

    receipt.title = name
    receipt.type = type or DEFAULT_TYPE
    if tax_code.strip():
        receipt.tax_code = tax_code.strip()
    receipt.category = category or DEFAULT_CATEGORY
    receipt.category_display = category_display or DEFAULT_CATEGORY_DISPLAY
    receipt.amount = amount_value
    receipt.date = date_value_parsed
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


@router.put("/receipt_categories/publish", response_model=ReceiptOut)
async def publish_receipt_category(
    payload: PublishIn | None = Body(None),
    repo: Repository = Depends(get_repository),
    user: User = Depends(get_current_user),
):
    """Публикация: Черновик -> Опубликован, дата формирования проставляется
    на бэкенде. Опубликовать можно только черновик, вернуть в черновик нельзя.

    Метод создателя — нужна авторизация (cookie session_id), иначе 401.
    """
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
    if "amount" in fields:
        receipt.amount = (
            Decimal(str(fields["amount"])).quantize(Decimal("0.01"))
            if fields["amount"] is not None
            else None
        )
    if "date" in fields:
        receipt.date = fields["date"]
    if "description" in fields:
        receipt.description = fields["description"]

    receipt.status = STATUS_PUBLISHED
    receipt.date_formed = datetime.now()
    await repo.save_receipt(receipt)
    return await _one_out(repo, user, receipt)


@router.delete("/receipt_categories/{receipt_category_id}", response_model=ReceiptOut)
async def delete_receipt_category(
    receipt_category_id: int,
    repo: Repository = Depends(get_repository),
    user: User = Depends(get_current_user),
):
    """Удаление услуги: только мягкое (status = «Удален») и только своих услуг.

    Метод создателя — нужна авторизация (cookie session_id), иначе 401.
    Вместе со статусом на бэкенде проставляется системная дата завершения —
    клиент её передавать не может.
    """
    receipt = await repo.get_receipt(receipt_category_id)
    if receipt is None or receipt.status == STATUS_DELETED:
        raise HTTPException(status_code=404)
    if receipt.id_user != user.id_user:
        raise HTTPException(status_code=403)

    receipt.status = STATUS_DELETED
    receipt.date_completed = datetime.now()
    await repo.save_receipt(receipt)
    return await _one_out(repo, user, receipt)


@router.post("/receipt_categories/{receipt_category_id}/like", response_model=ReceiptOut)
async def like_receipt_category(
    receipt_category_id: int,
    payload: dict | None = Body(None, description='{"value": 1} — поставить лайк, {"value": 0} — снять'),
    value: int | None = Query(None, description="0 — снять лайк, 1 — поставить"),
    repo: Repository = Depends(get_repository),
    user: User = Depends(get_current_user),
):
    """Лайк от текущего пользователя: value = 1 ставит лайк, value = 0 снимает.

    Метод создателя — нужна авторизация (cookie session_id), иначе 401:
    лайк всегда принадлежит пользователю из сессии.
    Любое другое value — 400 Bad Request."""
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

@router.post("/users/register", response_model=UserOut, status_code=201, tags=["Пользователи"])
async def register_user(
    payload: UserIn,
    response: Response,
    repo: Repository = Depends(get_repository),
):
    """Регистрация нового пользователя (аутентификация + автовход).

    Логин и пароль проверяются на сервере: свободно — создаётся пользователь,
    занято — 409 Conflict. Учётные данные с клиента не передаются.
    После успешной регистрации сразу создаётся сессия в Redis, её
    идентификатор возвращается в cookie session_id (HttpOnly) — вход уже
    выполнен, методы создателя доступны без отдельного login.
    """
    if await repo.get_user_by_login(payload.username) is not None:
        raise HTTPException(status_code=409)

    user = await repo.create_user(payload.username, payload.password)
    session_id = await sessions.create_session(user.id_user, user.username)
    _set_session_cookie(response, session_id)
    return UserOut(id_user=user.id_user, username=user.username)


@router.post("/users/login", response_model=UserOut, tags=["Пользователи"])
async def login_user(
    payload: UserIn,
    response: Response,
    repo: Repository = Depends(get_repository),
):
    """Аутентификация: проверка логина и пароля, открытие сессии.

    Пользователь не найден — 404, неверный пароль — 403. При успехе в Redis
    создаётся сессия (ключ session:<ид>, значение «id_user|username», TTL
    24 часа), клиенту возвращается тот же JSON и cookie session_id (HttpOnly) —
    этот cookie используется дальше в Swagger (кнопка Authorize) и в
    Postman/Insomnia (заголовок Cookie: session_id=...).
    """
    user = await repo.get_user_by_login(payload.username)
    if user is None:
        raise HTTPException(status_code=404)
    if user.password != payload.password:
        raise HTTPException(status_code=403)

    session_id = await sessions.create_session(user.id_user, user.username)
    _set_session_cookie(response, session_id)
    return UserOut(id_user=user.id_user, username=user.username)


@router.post("/users/logout", tags=["Пользователи"])
async def logout_user(
    response: Response,
    session_id: str | None = Cookie(None, alias=settings.SESSION_COOKIE),
):
    """Деавторизация: сессия удаляется из Redis, cookie — из ответа.

    После выхода методы создателя возвращают 401 Unauthorized. Повторный
    вызов без cookie — не ошибка: 200 с пустым телом («уже вышли»).
    Метод обязателен по методичке, в 10 запросов Postman-коллекции отчёта не входит.
    """
    await sessions.delete_session(session_id)
    response.delete_cookie(settings.SESSION_COOKIE)
    return {}

