"""Статусы услуг и значения по умолчанию.

Статус живёт только в БД: он нужен бизнес-логике (какие записи показывать),
но в JSON клиенту не передаётся — в приложении это разные окна.
Переходы между статусами разрешены только через отдельные методы API:
    Черновик   --PUT /api/receipt_categories/publish--> Опубликован
    Опубликован/Черновик --DELETE /api/receipt_categories/{id}--> Удален
Обратный переход в черновик не предусмотрен.
"""

STATUS_DRAFT = "Черновик"
STATUS_PUBLISHED = "Опубликован"
STATUS_DELETED = "Удален"

DEFAULT_TYPE = "income"
DEFAULT_CATEGORY = "debit"
DEFAULT_CATEGORY_DISPLAY = "Дебиторка"

# Заглушки для услуг, у которых файл ещё не загружен в MinIO
DEFAULT_IMAGE_URL = "/static/media/default.jpg"
DEFAULT_VIDEO_URL = "/static/media/default.mp4"
