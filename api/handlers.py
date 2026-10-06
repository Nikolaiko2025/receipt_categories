from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from data.collections import receipt_categories, get_published, get_by_id, get_next_after

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
def root_redirect():
    return RedirectResponse(url="/feed", status_code=303)


@router.get("/feed")
def get_feed(request: Request):
    published = get_published()
    
    if not published:
        return templates.TemplateResponse(
            request=request,
            name="receipt_categories_feed.html",
            context={"receipt_categories": [], "active_tab": "feed"}
        )
    
    first_rc = published[0]
    next_rc = get_next_after(first_rc["id_receipt_category"])
    
    return templates.TemplateResponse(
        request=request,
        name="receipt_categories_feed.html",
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
            name="receipt_categories_feed.html",
            context={"receipt_categories": [], "active_tab": "feed"}
        )
    
    next_rc = get_next_after(rc["id_receipt_category"])
    
    return templates.TemplateResponse(
        request=request,
        name="receipt_categories_feed.html",
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
        name="receipt_categories_add.html", 
        context={}
    )

@router.get("/grid")
def get_grid(request: Request, type: str = Query(default=None)):
    op_type = "income" if (type or "").strip().lower() == "income" else "expense"

    items = [rc for rc in get_published() if rc["type"] == op_type]

    return templates.TemplateResponse(
        request=request,
        name="receipt_categories_grid.html",
        context={
            "receipt_categories": items,
            "op_type": op_type,
            "active_tab": "grid"
        }
    )
