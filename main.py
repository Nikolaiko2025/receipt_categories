from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
import uvicorn
from api.handlers import router
from api.rest import router as api_router

app = FastAPI(
    title="Веб-сервис «Чеки» (receipt_categories)",
    version="4.0",
    description=(
        "REST API для SPA: услуги (чеки), пользователи, лайки.\n\n"
        "**Аутентификация** — сессии в Redis + cookie: "
        "`POST /api/users/register` и `POST /api/users/login` проверяют логин "
        "и пароль, создают сессию в Redis (ключ `session:<ид>`, значение "
        "`id_user|username`, TTL 24 часа) и возвращают cookie `session_id` "
        "(HttpOnly). `POST /api/users/logout` удаляет сессию и cookie.\n\n"
        "**Авторизация**: без cookie доступно только чтение — список услуг и "
        "лента (гость: `is_creator = 0`, `liked = 0`). Методы создателя "
        "(добавление, публикация, удаление, лайк, черновик) без валидной "
        "сессии возвращают `401 Unauthorized`. В Swagger нажмите Authorize "
        "и передайте значение cookie `session_id`, полученное при входе; "
        "в Postman/Insomnia — заголовок `Cookie: session_id=...` "
        "(значение куки видно во вкладке Application браузера)."
    ),
    openapi_tags=[
        {
            "name": "Услуги",
            "description": (
                "Домен «услуга»: список с фильтрами и лента доступны без "
                "авторизации; добавление, черновик, публикация, удаление и "
                "лайк — методы создателя, требуют cookie session_id."
            ),
        },
        {
            "name": "Пользователи",
            "description": (
                "Домен «пользователь»: регистрация и аутентификация открывают "
                "сессию в Redis и возвращают cookie session_id, деавторизация "
                "закрывает её."
            ),
        },
    ],
)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(router)      # серверные страницы (лаб. 1-2)
app.include_router(api_router)  # веб-сервис /api (лаб. 3)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Ошибка — только код состояния (404, 403, 405, 409...), тело пустое.

    Ни сообщений приложения, ни дублирования кода состояния в JSON нет.
    """
    return JSONResponse(status_code=exc.status_code, content={}, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError):
    """Ошибки разбора запроса (неверный ид, сумма, дата, не все поля) —
    это ошибка клиента, поэтому 400 Bad Request с пустым телом: только код,
    без сообщений и без дублирования кода состояния."""
    return JSONResponse(status_code=400, content={})

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
