from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from db.session import get_db, engine
from models.receipt_categories import Receipt_categories
from models.like import Like

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/feed")
async def get_feed(request: Request, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Receipt_categories)
        .options(selectinload(Receipt_categories.likes))
        .where(Receipt_categories.status == "Опубликован")
        .order_by(Receipt_categories.id_receipt_category)
        .limit(1)
    )
    result = await db.execute(stmt)
    first_receipt_category = result.scalar_one_or_none()

    if not first_receipt_category:
        return templates.TemplateResponse(
            request=request,
            name="feed.html",
            context={"receipt_categories": [], "active_tab": "feed"}
        )

    next_rc = await _get_next_after(db, first_receipt_category.id_receipt_category)

    return templates.TemplateResponse(
        request=request,
        name="feed.html",
        context={
            "receipt_categories": [first_receipt_category],
            "next_receipt_category": next_rc,
            "active_tab": "feed"
        }
    )


@router.get("/feed/{receipt_category_id}")
async def get_feed_by_id(
    request: Request,
    receipt_category_id: int,
    next: bool = False,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Receipt_categories)
        .options(selectinload(Receipt_categories.likes))
        .where(Receipt_categories.id_receipt_category == receipt_category_id)
    )
    current = result.scalar_one_or_none()

    if next:
        if current:
            next_rc = await _get_next_after(db, receipt_category_id)
            if next_rc:
                receipt_category = next_rc
            else:
                receipt_category = current
        else:
            receipt_category = await _get_first_published(db)
    else:
        if not current or current.status != "Опубликован":
            receipt_category = await _get_first_published(db)
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
def root(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="add.html",
        context={}
    )


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
        asyncpg_conn = raw.dbapi_connection.driver_connection
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
    result = await db.execute(
        select(Receipt_categories)
        .options(selectinload(Receipt_categories.likes))
        .where(Receipt_categories.status == "Опубликован")
        .order_by(Receipt_categories.id_receipt_category)
    )
    published = result.scalars().all()

    for i, rc in enumerate(published):
        if rc.id_receipt_category == receipt_category_id:
            if i + 1 < len(published):
                return published[i + 1]
            return None
    return None