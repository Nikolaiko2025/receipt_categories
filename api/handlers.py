from fastapi import APIRouter, Request, Query
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from data.collections import operations_db, get_published, get_by_id, get_next_after

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
            name="feed.html",
            context={"operations": [], "active_tab": "feed"}
        )
    
    first_operation = published[0]
    next_op = get_next_after(first_operation["id"])
    
    return templates.TemplateResponse(
        request=request,
        name="feed.html",
        context={
            "operations": [first_operation],
            "next_operation": next_op,
            "active_tab": "feed"
        }
    )

@router.get("/feed/{operation_id}")
def get_feed_by_id(request: Request, operation_id: int, next: bool = False):
    published = get_published()
    
    if next:
        current = get_by_id(operation_id)
        if current:
            next_op = get_next_after(operation_id)
            if next_op:
                operation = next_op
            else:
                operation = current
        else:
            operation = published[0] if published else None
    else:
        operation = get_by_id(operation_id)
        if not operation or operation["status"] != "Опубликован":
            operation = published[0] if published else None
    
    if not operation:
        return templates.TemplateResponse(
            request=request,
            name="feed.html",
            context={"operations": [], "active_tab": "feed"}
        )
    
    next_op = get_next_after(operation["id"])
    
    return templates.TemplateResponse(
        request=request,
        name="feed.html",
        context={
            "operations": [operation],
            "next_operation": next_op,
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
def get_grid(request: Request, filter: str = Query(None)):
    """Страница плитки со списком всех опубликованных операций"""
    published = get_published()
    filter_value = filter or ""
    
    # Фильтрация по сумме (если есть параметр filter)
    if filter:
        try:
            if filter.startswith('>='):
                value = float(filter[2:])
                published = [op for op in published if op["amount"] >= value]
            elif filter.startswith('<='):
                value = float(filter[2:])
                published = [op for op in published if op["amount"] <= value]
            elif filter.startswith('>'):
                value = float(filter[1:])
                published = [op for op in published if op["amount"] > value]
            elif filter.startswith('<'):
                value = float(filter[1:])
                published = [op for op in published if op["amount"] < value]
            else:
                value = float(filter)
                published = [op for op in published if op["amount"] >= value]
        except ValueError:
            # Если не удалось преобразовать в число, игнорируем фильтр
            pass
    
    return templates.TemplateResponse(
        request=request,
        name="grid.html",
        context={
            "operations": published,
            "filter_value": filter_value,
            "active_tab": "grid"
        }
    )
