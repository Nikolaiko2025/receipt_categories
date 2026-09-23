from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import get_db, engine
from models.receipt_categories import Receipt_categories
from models.like import Like

router = APIRouter()
templates = Jinja2Templates(directory="templates")

CURRENT_USER = "test_user"
DEFAULT_IMAGE_URL = "/static/media/default.jpg"
DEFAULT_VIDEO_URL = "/static/media/default.mp4"

templates.env.globals["default_image_url"] = DEFAULT_IMAGE_URL
templates.env.globals["default_video_url"] = DEFAULT_VIDEO_URL


@router.get("/feed")
@router.get("/feed/{receipt_category_id}")
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
            return RedirectResponse("/feed", status_code=302)

        if next:
            receipt_category = await _get_next_after(db, receipt_category_id) or current
        else:
            receipt_category = current

    if not receipt_category:
        return templates.TemplateResponse(
            request=request,
            name="feed.html",
            context={"receipt_categories": [], "active_tab": "feed"}
        )

    next_rc = await _get_next_after(db, receipt_category.id_receipt_category)

    return templates.TemplateResponse(
        request=request,
        name="feed.html",
        context={
            "receipt_categories": [receipt_category],
            "next_receipt_category": next_rc,
            "active_tab": "feed"
        }
    )


@router.get("/add")
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
        name="add.html",
        context={
            "draft": draft,
            "has_draft": draft is not None,
        },
    )


@router.post("/add")
async def post_add(
    title: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    existing_result = await db.execute(
        select(Receipt_categories)
        .where(Receipt_categories.status == "Черновик")
        .where(Receipt_categories.creator == CURRENT_USER)
        .limit(1)
    )
    existing_draft = existing_result.scalar_one_or_none()

    if existing_draft is not None:
        if title.strip():
            existing_draft.title = title.strip()
        await db.commit()
        return RedirectResponse("/add", status_code=303)

    draft = Receipt_categories(
        title=title.strip(),
        type="income",
        category="debit",
        category_display="Дебиторка",
        status="Черновик",
        image_url=DEFAULT_IMAGE_URL,
        video_url=DEFAULT_VIDEO_URL,
        date_created=datetime.now(),
        creator=CURRENT_USER,
    )
    db.add(draft)
    await db.commit()

    return RedirectResponse("/add", status_code=303)


@router.post("/publish")
async def post_publish(
    amount: str = Form(""),
    date_value: str = Form("", alias="date"),
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
        return RedirectResponse("/add", status_code=303)

    draft.amount = (
        Decimal(amount.replace(" ", "").replace(",", ".")) if amount.strip() else None
    )
    draft.date = date.fromisoformat(date_value) if date_value.strip() else None
    draft.description = description.strip() or None
    draft.status = "Опубликован"
    draft.date_formed = datetime.now()
    await db.commit()

    return RedirectResponse("/feed", status_code=303)


@router.get("/grid")
async def get_grid(request: Request, search: str = "", db: AsyncSession = Depends(get_db)):
    """Страница плитки со списком всех опубликованных чеков"""
    stmt = select(Receipt_categories).options(selectinload(Receipt_categories.likes)).where(Receipt_categories.status == "Опубликован")

    if search:
        parts = search.split(";")
        if len(parts) == 2:
            try:
                if parts[0] == "" and parts[1] != "":
                    stmt = stmt.where(Receipt_categories.amount <= float(parts[1]))
                elif parts[1] == "" and parts[0] != "":
                    stmt = stmt.where(Receipt_categories.amount >= float(parts[0]))
                elif parts[0] != "" and parts[1] != "":
                    stmt = stmt.where(
                        Receipt_categories.amount >= float(parts[0]),
                        Receipt_categories.amount <= float(parts[1]),
                    )
            except ValueError:
                pass

    filter_options = [
        {"value": "", "label": "Все"},
        {"value": ";-500000", "label": "до -500 000"},
        {"value": "-500000;-200000", "label": "от -500 000 до -200 000"},
        {"value": "-200000;0", "label": "от -200 000 до 0"},
        {"value": "0;200000", "label": "от 0 до 200 000"},
        {"value": "200000;500000", "label": "от 200 000 до 500 000"},
        {"value": "500000;1000000", "label": "от 500 000 до 1 000 000"},
        {"value": "1000000;", "label": "от 1 000 000"},
    ]
    for opt in filter_options:
        opt["selected"] = search == opt["value"]
    filter_label = next((opt["label"] for opt in filter_options if opt["selected"]), "Все")

    result = await db.execute(stmt)
    receipt_categories = result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="grid.html",
        context={
            "receipt_categories": receipt_categories,
            "search": search,
            "filter_options": filter_options,
            "filter_label": filter_label,
            "active_tab": "grid"
        }
    )


@router.post("/grid/{receipt_category_id}/delete")
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
                "UPDATE receipt_categories SET status = 'Удален' WHERE id_receipt_category = $1",
                receipt_category_id,
            )
    return RedirectResponse("/grid", status_code=303)


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