from datetime import date as _date
from datetime import datetime as _datetime
from pydantic import BaseModel, Field

class ReceiptOut(BaseModel):
    id_receipt_category: int
    title: str
    type: str | None = Field(None, description="income — поступление, expense — выплата")
    tax_code: str | None = Field(None, description="код операции, например 01 или 02")
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
    id_receipt_category: int | None = None
    # income — поступление, expense — выплата
    type: str | None = Field(None, description="income — поступление, expense — выплата")
    tax_code: str | None = Field(None, max_length=20, description="код операции, например 01")
    amount: float | None = None
    date: _date | None = None
    description: str | None = None
