from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import APIRouter, Request, Depends, File, Form, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from core import storage
from db.session import get_db, engine
from core.current_user import get_current_user
from models.receipt_categories import Receipt_categories
from models.like import Like

router = APIRouter()
templates = Jinja2Templates(directory="templates")

CURRENT_USER = "test_user"
DEFAULT_IMAGE_URL = "/static/media/default.jpg"
DEFAULT_VIDEO_URL = "/static/media/default.mp4"
TYPES = ("income", "expense")

templates.env.globals["default_image_url"] = DEFAULT_IMAGE_URL
templates.env.globals["default_video_url"] = DEFAULT_VIDEO_URL
# имя файла в MinIO -> публичный URL (старые пути до статики возвращаются как есть)
templates.env.globals["public_url"] = storage.public_url


async def _save_upload(upload: UploadFile | None, kind: str) -> str | None:
    """Читает файл из формы, генерирует латинское имя и кладёт его в MinIO."""
    if upload is None or not upload.filename:
        return None
    data = await upload.read()
    if not data:
        return None
    name = storage.generate_name(upload.filename, upload.content_type or "", kind)
    storage.upload(data, name, upload.content_type or "")
    return name


@router.get("/")
async def root():
    """Корень сайта — редирект на ленту."""
    return RedirectResponse("/receipt_categories_feed", status_code=303)


@router.get("/receipt_categories_feed")
@router.get("/receipt_categories_feed/{receipt_category_id}")
async def get_feed(
    request: Request,
    receipt_category_id: int | None = None,
    next: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Лента. БД возвращает одну строку (LIMIT 1). `next=true` — следующая
    опубликованная услуга, удалённая/чернововая услуга по URL не показывается."""
    if receipt_category_id is None:
        receipt_category = await _get_first_published(db)
    else:
        result = await db.execute(
            select(Receipt_categories)
            .options(selectinload(Receipt_categories.likes))
            .where(Receipt_categories.id_receipt_category == receipt_category_id)
        )
        current = result.scalar_one_or_none()

        if current is None or current.status != "Опубликован":
            return RedirectResponse("/receipt_categories_feed", status_code=302)

        if next:
            receipt_category = await _get_next_after(db, receipt_category_id) or current
        else:
            receipt_category = current

    if not receipt_category:
        return templates.TemplateResponse(
            request=request,
            name="receipt_categories_feed.html",
            context={"receipt_categories": [], "active_tab": "feed"}
        )

    next_rc = await _get_next_after(db, receipt_category.id_receipt_category)

    return templates.TemplateResponse(
        request=request,
        name="receipt_categories_feed.html",
        context={
            "receipt_categories": [receipt_category],
            "next_receipt_category": next_rc,
            "active_tab": "feed"
        }
    )


@router.get("/receipt_categories_add")
async def get_add(request: Request, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Receipt_categories)
        .where(Receipt_categories.status == "Черновик")
        .where(Receipt_categories.creator == CURRENT_USER)
        .order_by(Receipt_categories.id_receipt_category)
        .limit(1)
    )
    result = await db.execute(stmt)
    draft = result.scalar_one_or_none()

    return templates.TemplateResponse(
        request=request,
        name="receipt_categories_add.html",
        context={
            "draft": draft,
            "has_draft": draft is not None,
        },
    )


@router.post("/receipt_categories_add")
async def post_add(
    title: str = Form(...),
    image: UploadFile | None = File(None),
    video: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
):
    existing_result = await db.execute(
        select(Receipt_categories)
        .where(Receipt_categories.status == "Черновик")
        .where(Receipt_categories.creator == CURRENT_USER)
        .limit(1)
    )
    existing_draft = existing_result.scalar_one_or_none()

    image_name = await _save_upload(image, "image")
    video_name = await _save_upload(video, "video")

    if existing_draft is not None:
        if title.strip():
            existing_draft.title = title.strip()
        if image_name:
            existing_draft.image_url = image_name
        if video_name:
            existing_draft.video_url = video_name
        await db.commit()
        return RedirectResponse("/receipt_categories_add", status_code=303)

    current_user = await get_current_user(db)
    draft = Receipt_categories(
        title=title.strip(),
        type="income",
        category="debit",
        category_display="Дебиторка",
        status="Черновик",
        image_url=image_name or DEFAULT_IMAGE_URL,
        video_url=video_name or DEFAULT_VIDEO_URL,
        date_created=datetime.now(),
        creator=CURRENT_USER,
        id_user=current_user.id_user,
    )
    db.add(draft)
    await db.commit()

    return RedirectResponse("/receipt_categories_add", status_code=303)


@router.post("/receipt_categories_publish")
async def post_publish(
    tax_code: str = Form(""),
    type: str = Form("income"),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Receipt_categories)
        .where(Receipt_categories.status == "Черновик")
        .where(Receipt_categories.creator == CURRENT_USER)
        .limit(1)
    )
    result = await db.execute(stmt)
    draft = result.scalar_one_or_none()

    if draft is None:
        return RedirectResponse("/receipt_categories_add", status_code=303)

    draft.tax_code = tax_code.strip() or None
    draft.type = type if type in TYPES else "income"
    draft.description = description.strip() or None
    draft.status = "Опубликован"
    draft.date_formed = datetime.now()
    await db.commit()

    return RedirectResponse("/receipt_categories_feed", status_code=303)


@router.get("/receipt_categories_grid")
async def get_grid(request: Request, expense: bool = False, db: AsyncSession = Depends(get_db)):
    """Плитка опубликованных операций. Фильтр одной галочкой:
    снята — Поступление (type = income), отмечена — Выплата (type = expense)."""
    stmt = (
        select(Receipt_categories)
        .options(selectinload(Receipt_categories.likes))
        .where(Receipt_categories.status == "Опубликован")
        .where(Receipt_categories.type == ("expense" if expense else "income"))
    )

    result = await db.execute(stmt)
    receipt_categories = result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="receipt_categories_grid.html",
        context={
            "receipt_categories": receipt_categories,
            "expense": expense,
            "active_tab": "grid"
        }
    )


@router.post("/receipt_categories_grid/{receipt_category_id}/delete")
async def delete_receipt_category(
    receipt_category_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Логическое удаление услуги через SQL UPDATE (raw-соединение asyncpg, без ORM)"""
    async with engine.connect() as connection:
        raw = await connection.get_raw_connection()
        asyncpg_conn = raw.driver_connection
        async with asyncpg_conn.transaction():
            await asyncpg_conn.execute(
                "UPDATE receipt_categories SET status = 'Удален', "
                "date_completed = now() WHERE id_receipt_category = $1",
                receipt_category_id,
            )
    return RedirectResponse("/receipt_categories_grid", status_code=303)


async def _get_first_published(db: AsyncSession):
    result = await db.execute(
        select(Receipt_categories)
        .options(selectinload(Receipt_categories.likes))
        .where(Receipt_categories.status == "Опубликован")
        .order_by(Receipt_categories.id_receipt_category)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _get_next_after(db: AsyncSession, receipt_category_id: int):
    """Следующая опубликованная услуга — БД возвращает одну строку (LIMIT 1)."""
    result = await db.execute(
        select(Receipt_categories)
        .options(selectinload(Receipt_categories.likes))
        .where(Receipt_categories.status == "Опубликован")
        .where(Receipt_categories.id_receipt_category > receipt_category_id)
        .order_by(Receipt_categories.id_receipt_category)
        .limit(1)
    )
    return result.scalar_one_or_none()