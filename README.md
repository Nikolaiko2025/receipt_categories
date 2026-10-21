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
| GET | /api/receipt_categories?type=&title=&expense=&mine= | Список опубликованных с фильтрацией на БД. Поля is_creator 0/1 — нужна ли кнопка удаления на плитке, liked 0/1 — лайкнута ли текущим пользователем |
| GET | /api/receipt_categories/feed?id_receipt_category=&next=true | Лента. Без параметров — первая опубликованная услуга, LIMIT 1. id_receipt_category — ид услуги, с которой показывать ленту; next=true — следующая опубликованная после указанного ид, на конце ленты — начинаем сначала. Нет такого ид, черновик или удалённая услуга — 404 |
| GET | /api/receipt_categories/draft | Получить черновик текущего пользователя, ид не указывается, не более 1 на пользователя. Нет черновика — 404 |
| POST | /api/receipt_categories | Создать черновик, multipart/form-data. Форма: title обязательно, type, description, изображение — файл, видео — файл. Если черновик уже есть — обновляется он. 201, 400 |
| PUT | /api/receipt_categories/publish | Опубликовать. JSON необязательно: id_receipt_category, description → Черновик → Опубликован. Нет, не свой или уже опубликован — 404 |
| DELETE | /api/receipt_categories/{id_receipt_category} | Мягкое удаление только своих услуг: status = Удален и системная date_completed. Ответ: 200 — услуга, 403 — чужая, 404 — нет или уже удалена |
| POST | /api/receipt_categories/{id_receipt_category}/like | Лайк. JSON {"value": 1} или query ?value=0: 1 — поставить, 0 — снять. Другое значение — 400 |

### Домен «пользователь»

| Метод | URL | Описание |
|---|---|---|
| POST | /api/users/register | Регистрация. JSON: username, password. 201 — пользователь, 409 — имя занято, 400 — пустые поля |
| POST | /api/users/login | Аутентификация — заглушка. 200 — пользователь, 404 — нет пользователя, 403 — неверный пароль |
| POST | /api/users/logout | Деавторизация — заглушка. Ответ: 200, пустое тело {} |
