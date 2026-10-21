## Описание методов для Swagger

### Домен «услуга»

| Метод | URL | Описание |
|---|---|---|
| GET | `/api/receipt_categories?type=&tax_code=&title=&expense=&mine=` | Список опубликованных услуг с фильтрацией. Поле `is_creator` (0/1) — создатель услуги совпадает с текущим пользователем. `mine=true` без входа — `401` |
| GET | `/api/receipt_categories/feed?id=` | Лента: услуга + данные следующей (`next_id_receipt_category`, `next_video_url`). Без `id` — первая опубликованная; с `id` — с этой услуги; после последней лента начинается сначала |
| GET | `/api/receipt_categories/draft` | Получить черновик текущего пользователя (не более 1 записи) |
| POST | `/api/receipt_categories` | Создать черновик. Форма: `title`, `type`, `tax_code`, `description`, `image` (файл), `video` (файл). Файлы — в MinIO, названия — в полях БД, генерируются на латинице |
| PUT | `/api/receipt_categories/publish` | Опубликовать (смена статуса). JSON: `id_receipt_category`, `type`, `tax_code`, `description` (все необязательные; без `id` — черновик текущего пользователя) |
| DELETE | `/api/receipt_categories/{id_receipt_category}` | Мягкое удаление (только своих). Ответ: `200` — услуга, `403` — чужая, `404` — нет |
| POST | `/api/receipt_categories/{id_receipt_category}/like` | Лайк. Поле `value` (1 = поставить, 0 = отменить) |

### Домен «пользователь»

| Метод | URL | Описание |
|---|---|---|
| POST | `/api/users/register` | Регистрация. JSON: `username`, `password`. Ответ `201` + cookie `session_id`; занятый логин — `409` |
| POST | `/api/users/login` | Аутентификация: проверка логина и пароля, сессия в Redis, cookie `session_id`; неверный пароль — `403`, нет пользователя — `404` |
| POST | `/api/users/logout` | Деавторизация: удаляет сессию из Redis и cookie; без cookie — завершает все сессии всех пользователей |
