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
    они вычисляются на бэкенде: пользователь берётся из функции-синглтона
    core.current_user, даты и статусы — из бизнес-логики;
  * в JSON нет отдельных сообщений об ошибках — код состояния возвращает
    сам HTTP-ответ: 200, 201, 400, 403, 404, 405, 409;
  * поля запросов и ответов — строго по README: лишние поля не принимаются
    и не показываются.
"""
from datetime import datetime

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api.serializers import PublishIn, ReceiptOut, UserIn, UserOut
from core import storage
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
from core.current_user import get_current_user
from db.repository import Repository
from db.session import get_db
from models.receipt_categories import Receipt_categories
from models.user import User

router = APIRouter(prefix="/api", tags=["api"])


# ---------------------------------------------------------------- dependencies

async def current_user(db: AsyncSession = Depends(get_db)) -> User:
    """Текущий пользователь — синглтон из core.current_user (константа)."""
    return await get_current_user(db)


def get_repository(db: AsyncSession = Depends(get_db)) -> Repository:
    """Repository работает в той же сессии, что и текущий пользователь."""
    return Repository(db)


# ---------------------------------------------------------------- helpers

def _to_out(
    receipt: Receipt_categories,
    user: User,
    liked: set[int],
) -> ReceiptOut:
    """Сборка JSON услуги — строго поля из README, набор всегда одинаковый.

    В ответ входят type — поступление или выплата, tax_code — код операции
    и status. Категория, сумма, даты и счётчик лайков в ответ не входят —
    они остались в БД: по ним работает фильтрация и страницы приложения.
    """
    return ReceiptOut(
        id_receipt_category=receipt.id_receipt_category,
        title=receipt.title or "",
        type=receipt.type or "",
        tax_code=receipt.tax_code,
        description=receipt.description,
        image_url=storage.public_url(receipt.image_url) or "",
        video_url=storage.public_url(receipt.video_url) or "",
        status=receipt.status or "",
        is_creator=1 if receipt.id_user == user.id_user else 0,
        liked=1 if receipt.id_receipt_category in liked else 0,
    )


async def _one_out(
    repo: Repository, user: User, receipt: Receipt_categories
) -> ReceiptOut:
    _counts, liked = await repo.likes_meta(user.id_user, [receipt])
    return _to_out(receipt, user, liked)


async def _many_out(
    repo: Repository, user: User, receipts: list[Receipt_categories]
) -> list[ReceiptOut]:
    _counts, liked = await repo.likes_meta(user.id_user, receipts)
    return [_to_out(receipt, user, liked) for receipt in receipts]


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


def _blank_to_none(raw: str | None) -> str | None:
    """Пустая строка или отсутствующий параметр — None: фильтр не применяется."""
    if raw is None:
        return None
    return raw.strip() or None


def _parse_optional_bool(raw: str | None) -> bool | None:
    """Пусто или отсутствует — None (без фильтра); true/1/yes/on — True;
    false/0/no/off — False; иное значение — 400 Bad Request."""
    value = (raw or "").strip().lower()
    if value == "":
        return None
    if value in {"true", "1", "yes", "on"}:
        return True
    if value in {"false", "0", "no", "off"}:
        return False
    raise HTTPException(status_code=400)


# ---------------------------------------------------------------- домен «услуга»

@router.get("/receipt_categories", response_model=list[ReceiptOut])
async def list_receipt_categories(
    type: str | None = Query(None, description="income — поступление, expense — выплата"),
    title: str | None = Query(None, description="поиск по названию (частичный, без учёта регистра)"),
    expense: str | None = Query(None, description="true — только выплаты, false — без выплат, пусто — без фильтра"),
    mine: str | None = Query(None, description="true — только услуги текущего пользователя, пусто — без фильтра"),
    repo: Repository = Depends(get_repository),
    user: User = Depends(current_user),
):
    """Список опубликованных услуг с фильтрацией на стороне БД — параметры как в README.

    is_creator 0/1 — нужна ли кнопка удаления на плитке, liked 0/1 — лайкнута ли
    услуга текущим пользователем. Пустое значение параметра — фильтр не применяется,
    мусорное — 400 Bad Request.
    """
    receipts = await repo.list_receipts(
        type=_blank_to_none(type),
        title=_blank_to_none(title),
        expense=_parse_optional_bool(expense),
        mine=_parse_optional_bool(mine),
        user_id=user.id_user,
    )
    return await _many_out(repo, user, receipts)


def _parse_next(raw: str | None) -> bool:
    """Пусто или отсутствует — False; true/1/yes/on — True; false/0/no/off — False;
    иное значение — 400 Bad Request."""
    return _parse_optional_bool(raw) or False


async def _feed_by_id(
    repo: Repository, user: User, receipt_id: int, next_flag: bool
) -> ReceiptOut:
    """Лента по ид: услуга с этим ид; next=true — следующая опубликованная.
    Несуществующий ид, черновик или удалённая услуга — 404, конец ленты — начинаем сначала."""
    current = await repo.get_receipt(receipt_id)
    if current is None or current.status != STATUS_PUBLISHED:
        raise HTTPException(status_code=404)

    if not next_flag:
        return await _one_out(repo, user, current)

    receipt = await repo.get_next_published(receipt_id)
    if receipt is None:  # конец ленты — начинаем сначала
        receipt = await repo.get_first_published()
    if receipt is None:
        raise HTTPException(status_code=404)
    return await _one_out(repo, user, receipt)


@router.get("/receipt_categories/feed", response_model=ReceiptOut)
async def feed(
    id_receipt_category: str | None = Query(
        None,
        description="ид услуги, число; пусто или без параметра — первая опубликованная услуга",
    ),
    next: str | None = Query(
        None,
        description="true — следующая опубликованная услуга после указанного ид",
    ),
    repo: Repository = Depends(get_repository),
    user: User = Depends(current_user),
):
    """Лента: без параметров — первая опубликованная услуга (LIMIT 1);
    по ид — услуга с этим ид; по ид и next=true — следующая опубликованная.
    Второй вариант того же метода — ид в пути адреса: /feed/{id}?next=true."""
    receipt_id: int | None = None
    if id_receipt_category:  # "" или отсутствует — лента без ид
        try:
            receipt_id = int(id_receipt_category)
        except ValueError:
            raise HTTPException(status_code=400)

    next_flag = _parse_next(next)

    if receipt_id is None:  # лента без ид
        receipt = await repo.get_first_published()
        if receipt is None:
            raise HTTPException(status_code=404)
        return await _one_out(repo, user, receipt)

    return await _feed_by_id(repo, user, receipt_id, next_flag)


@router.get("/receipt_categories/feed/{receipt_category_id}", response_model=ReceiptOut)
async def feed_by_path(
    receipt_category_id: int,
    next: str | None = Query(
        None,
        description="true — следующая опубликованная услуга после указанного ид",
    ),
    repo: Repository = Depends(get_repository),
    user: User = Depends(current_user),
):
    """Лента по ид в пути адреса — второй вариант вызова того же метода:
    next=true — следующая опубликованная услуга (LIMIT 1);
    несуществующий ид — 404, конец ленты — начинаем сначала."""
    return await _feed_by_id(repo, user, receipt_category_id, _parse_next(next))


@router.get("/receipt_categories/draft", response_model=ReceiptOut)
async def get_draft(
    repo: Repository = Depends(get_repository),
    user: User = Depends(current_user),
):
    """Поля черновика: ид не указывается, запись не более 1 на пользователя."""
    receipt = await repo.get_draft(user.id_user)
    if receipt is None:
        raise HTTPException(status_code=404)
    return await _one_out(repo, user, receipt)


@router.post("/receipt_categories", response_model=ReceiptOut, status_code=201)
async def create_receipt_category(
    title: str = Form(..., max_length=100, description="название услуги"),
    type: str = Form(DEFAULT_TYPE, max_length=20, description="income — поступление, expense — выплата"),
    description: str = Form("", description="описание операции"),
    image: UploadFile | None = File(None, description="файл изображения"),
    video: UploadFile | None = File(None, description="файл короткого видео"),
    repo: Repository = Depends(get_repository),
    user: User = Depends(current_user),
):
    """Добавление услуги (multipart/form-data) — форма строго по README:
    title обязательно, type, description, изображение — файл, видео — файл.

    Файлы уходят в MinIO, в БД сохраняются их сгенерированные латинские имена.
    Создаётся не более одного черновика на пользователя: если черновик уже есть,
    обновляется он. Сумма, дата, категория и статус с клиента не принимаются —
    они проставляются на бэкенде.
    """
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
            image_url=DEFAULT_IMAGE_URL,
            video_url=DEFAULT_VIDEO_URL,
            category=DEFAULT_CATEGORY,
            category_display=DEFAULT_CATEGORY_DISPLAY,
        )

    receipt.title = name
    receipt.type = type or DEFAULT_TYPE
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
    user: User = Depends(current_user),
):
    """Публикация: Черновик -> Опубликован, дата формирования проставляется
    на бэкенде. JSON необязательно: id_receipt_category, description — строго
    по README. Опубликовать можно только черновик, вернуть в черновик нельзя."""
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
    user: User = Depends(current_user),
):
    """Удаление услуги: только мягкое (status = «Удален») и только своих услуг.

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
    user: User = Depends(current_user),
):
    """Лайк от текущего пользователя: value = 1 ставит лайк, value = 0 снимает.
    Любое другое value — 400 Bad Request."""
    receipt = await repo.get_receipt(receipt_category_id)
    if receipt is None or receipt.status != STATUS_PUBLISHED:
        raise HTTPException(status_code=404)

    raw = value
    if raw is None and payload:
        raw = payload.get("value")
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

@router.post("/users/register", response_model=UserOut, status_code=201)
async def register_user(
    payload: UserIn,
    repo: Repository = Depends(get_repository),
):
    """Регистрация нового пользователя."""
    if await repo.get_user_by_login(payload.username) is not None:
        raise HTTPException(status_code=409)

    user = await repo.create_user(payload.username, payload.password)
    return UserOut(id_user=user.id_user, username=user.username)


@router.post("/users/login", response_model=UserOut)
async def login_user(payload: UserIn, repo: Repository = Depends(get_repository)):
    """Аутентификация — заглушка для 4-й лабораторной (без токенов)."""
    user = await repo.get_user_by_login(payload.username)
    if user is None:
        raise HTTPException(status_code=404)
    if user.password != payload.password:
        raise HTTPException(status_code=403)
    return UserOut(id_user=user.id_user, username=user.username)


@router.post("/users/logout")
async def logout_user() -> dict:
    """Деавторизация — заглушка для 4-й лабораторной: токенов нет.

    Ответ — 200 и пустое тело {} (строго по README)."""
    return {}

