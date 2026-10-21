# receipt_categories — REST API

## Таблицы БД

### receipt_categories

| Поле | Тип | Описание |
|---|---|---|
| id_receipt_category | INTEGER PK | Идентификатор, генерируется БД |
| title | VARCHAR(100) | Название |
| type | VARCHAR(20) | Тип операции: income — поступление, expense — выплата |
| description | TEXT | Описание |
| status | VARCHAR(11) | Статус: Черновик / Опубликован / Удален |
| image_url | VARCHAR(255) | Имя файла изображения в MinIO |
| video_url | VARCHAR(255) | Имя файла видео в MinIO |
| date_created | DATETIME | Дата создания |
| creator | VARCHAR(50) | Логин создателя |
| date_formed | DATETIME | Дата публикации |
| id_user | INTEGER FK | Создатель → users.id_user |
| date_completed | DATETIME | Дата удаления |
| tax_code | VARCHAR(20) | Код операции, вводится пользователем в интерфейсе |

### users

| Поле | Тип | Описание |
|---|---|---|
| id_user | INTEGER PK | Идентификатор |
| username | VARCHAR(50) | Логин, уникальность проверяется при регистрации |
| password | VARCHAR(255) | Пароль |

### likes

| Поле | Тип | Описание |
|---|---|---|
| id_user | INTEGER PK | Пользователь, без FK в БД, связь задана в модели ORM |
| id_receipt_category | INTEGER FK | Услуга, без FK в БД, связь задана в модели ORM |
| id_like | INTEGER FK | Идентификатор лайка, генерируется sequence |

## HTTP-методы

### Домен «услуга»

| Метод | URL | Описание |
|---|---|---|
| GET | /api/receipt_categories?type=&title=&expense=&mine= | Список опубликованных с фильтрацией. Поле is_creator (0/1) — создатель услуги совпадает с текущим пользователем |
| GET | /api/receipt_categories/feed?id_receipt_category=&next=true | Лента: услуга + есть ли лайк (liked 0/1). Без id — первая опубликованная; с id_receipt_category — с этой услуги; next=true — следующая |
| GET | /api/receipt_categories/draft | Получить черновик текущего пользователя (не более 1 записи) |
| POST | /api/receipt_categories | Создать черновик. Форма: title, type, description, image (файл), video (файл). Файлы — в MinIO, названия — в полях БД, генерируются на латинице |
| PUT | /api/receipt_categories/publish | Опубликовать (смена статуса). JSON: id_receipt_category, description (необязательно) |
| DELETE | /api/receipt_categories/{id_receipt_category} | Мягкое удаление (только своих). Ответ: 200 — услуга, 403 — чужая, 404 — нет |
| POST | /api/receipt_categories/{id_receipt_category}/like | Лайк. Поле value (1 = поставить, 0 = отменить) |

### Домен «пользователь»

| Метод | URL | Описание |
|---|---|---|
| POST | /api/users/register | Регистрация. JSON: username, password |
| POST | /api/users/login | Аутентификация (заглушка) |
| POST | /api/users/logout | Деавторизация (заглушка) |
