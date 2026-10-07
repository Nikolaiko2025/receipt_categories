"""Сериализаторы — Pydantic-схемы веб-сервиса.

ReceiptOut — единый формат услуги для ВСЕХ методов: один и тот же набор полей,
независимо от того, список это, лента, черновик или ответ на публикацию.
Поле status (оно нужно только БД) в JSON не входит, системные поля
(id, создатель, даты) клиентом на изменение не передаются.
Поля type, category, category_display и date (дата операции) в сервисе есть:
в них хранятся данные и по ним работает фильтрация, но клиенту они не отдаются
— набор ключей ответа всегда одинаков (12 полей).
"""
from datetime import date as _date
from datetime import datetime as _datetime

from pydantic import BaseModel, Field


class ReceiptOut(BaseModel):
    id_receipt_category: int
    title: str
    amount: float | None = None
    description: str | None = None
    image_url: str
    video_url: str
    date_created: _datetime | None = None
    date_formed: _datetime | None = None
    date_completed: _datetime | None = None
    likes: int = 0
    is_creator: int = Field(0, description="1 — услуга принадлежит текущему пользователю")
    liked: int = Field(0, description="1 — текущий пользователь поставил лайк")


class UserOut(BaseModel):
    id_user: int
    username: str


class UserIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=255)


class PublishIn(BaseModel):
    """Публикация: можно уточнить поля и указать ид черновика (необязательно)."""
    id_receipt_category: int | None = None
    amount: float | None = None
    date: _date | None = None
    description: str | None = None
