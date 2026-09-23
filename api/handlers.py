from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from data.collections import receipt_categories, get_published, get_by_id, get_next_after

router = APIRouter()
templates = Jinja2Templates(directory="templates")

AMOUNT_RANGES = [
    {"value": "amt:btw:-500000:-200000", "label": "от −500 000 до −200 000"},
    {"value": "amt:btw:-200000:0", "label": "от −200 000 до 0"},
    {"value": "amt:lt:500000", "label": "До 500 000 ₽"},
    {"value": "amt:btw:500000:1000000", "label": "500 000 – 1 000 000 ₽"},
    {"value": "amt:gt:1000000", "label": "Более 1 000 000 ₽"},
]


@router.get("/")
def root_redirect():
    return RedirectResponse(url="/feed", status_code=303)


@router.get("/feed")
def get_feed(request: Request):
    published = get_published()
    
    if not published:
        return templates.TemplateResponse(
            request=request,
            name="feed.html",
            context={"receipt_categories": [], "active_tab": "feed"}
        )
    
    first_rc = published[0]
    next_rc = get_next_after(first_rc["id_receipt_category"])
    
    return templates.TemplateResponse(
        request=request,
        name="feed.html",
        context={
            "receipt_categories": [first_rc],
            "next_rc": next_rc,
            "active_tab": "feed"
        }
    )

@router.get("/feed/{receipt_category_id}")
def get_feed_by_id(request: Request, receipt_category_id: int, next: bool = False):
    published = get_published()
    
    if next:
        current = get_by_id(receipt_category_id)
        if current:
            next_rc = get_next_after(receipt_category_id)
            if next_rc:
                rc = next_rc
            else:
                rc = current
        else:
            rc = published[0] if published else None
    else:
        rc = get_by_id(receipt_category_id)
        if not rc or rc["status"] != "Опубликован":
            rc = published[0] if published else None
    
    if not rc:
        return templates.TemplateResponse(
            request=request,
            name="feed.html",
            context={"receipt_categories": [], "active_tab": "feed"}
        )
    
    next_rc = get_next_after(rc["id_receipt_category"])
    
    return templates.TemplateResponse(
        request=request,
        name="feed.html",
        context={
            "receipt_categories": [rc],
            "next_rc": next_rc,
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
def get_grid(request: Request, search: str = None):
    """Страница плитки со списком всех опубликованных операций"""
    published = get_published()
    selected = (search or "").strip() or "all"

    # Формируем варианты фильтра (диапазоны сумм)
    options = [{"label": "Все операции", "value": "all", "selected": selected == "all"}]
    for item in AMOUNT_RANGES:
        options.append({"value": item["value"], "label": item["label"], "selected": selected == item["value"]})

    filter_label = next((o["label"] for o in options if o["selected"]), "Все операции")

    # Фильтрация по выбранному диапазону суммы (значения со знаком)
    if selected.startswith("amt:"):
        parts = selected.split(":")
        if parts[1] == "lt":
            value = float(parts[2])
            published = [rc for rc in published if rc["amount"] is not None and rc["amount"] < value]
        elif parts[1] == "btw":
            lo, hi = float(parts[2]), float(parts[3])
            published = [rc for rc in published if rc["amount"] is not None and lo <= rc["amount"] < hi]
        elif parts[1] == "gt":
            value = float(parts[2])
            published = [rc for rc in published if rc["amount"] is not None and rc["amount"] >= value]

    return templates.TemplateResponse(
        request=request,
        name="grid.html",
        context={
            "receipt_categories": published,
            "filter_label": filter_label,
            "filter_options": options,
            "active_tab": "grid"
        }
    )
