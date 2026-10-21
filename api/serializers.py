from datetime import datetime as _datetime

from pydantic import BaseModel, Field, field_validator


class ReceiptOut(BaseModel):
    id_receipt_category: int
    title: str
    type: str | None = Field(None, description="income — поступление, expense — выплата")
    tax_code: str | None = Field(None, description="код операции, например 01 или 02")
    description: str | None = None
    image_url: str
    video_url: str
    date_created: _datetime | None = None
    date_formed: _datetime | None = None
    date_completed: _datetime | None = None
    likes: int = 0
    is_creator: int = Field(0, description="1 — услуга принадлежит текущему пользователю")
    liked: int = Field(0, description="1 — текущий пользователь поставил лайк")


class FeedOut(ReceiptOut):
    """Лента: текущая услуга плюс ид и видео следующей (лента зациклена)."""

    next_id_receipt_category: int | None = Field(
        None, description="ид следующей опубликованной услуги в ленте"
    )
    next_video_url: str = Field(
        "", description="видео следующей услуги — можно предзагрузить заранее"
    )


class UserOut(BaseModel):
    id_user: int
    username: str


class UserIn(BaseModel):
    username: str = Field(
        min_length=1,
        max_length=50,
        description="логин пользователя; должен быть уникальным",
    )
    password: str = Field(
        min_length=1,
        max_length=255,
        description="пароль; не более 72 байт, на сервере хранится как bcrypt-хеш",
    )

    @field_validator("password")
    @classmethod
    def password_within_bcrypt_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("пароль не должен превышать 72 байта")
        return value


class PublishIn(BaseModel):
    id_receipt_category: int | None = Field(
        None,
        description="ид черновика; можно не указывать — будет найден черновик текущего пользователя",
    )
    # income — поступление, expense — выплата
    type: str | None = Field(None, description="income — поступление, expense — выплата")
    tax_code: str | None = Field(None, max_length=20, description="код операции, например 01")
    description: str | None = Field(None, description="описание услуги")
