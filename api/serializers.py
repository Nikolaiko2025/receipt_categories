from pydantic import BaseModel, Field


class ReceiptOut(BaseModel):
    """JSON услуги — строго поля из README: без суммы, дат и счётчика лайков."""

    id_receipt_category: int
    title: str
    type: str = ""
    tax_code: str | None = None
    description: str | None = None
    image_url: str
    video_url: str
    status: str = ""
    is_creator: int = Field(0, description="1 — услуга принадлежит текущему пользователю")
    liked: int = Field(0, description="1 — текущий пользователь поставил лайк")


class UserOut(BaseModel):
    """JSON пользователя — как в README: id_user, username (без пароля)."""

    id_user: int
    username: str


class UserIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=255)


class PublishIn(BaseModel):
    """JSON публикации — строго по README: id_receipt_category и description, оба необязательны."""

    id_receipt_category: int | None = None
    description: str | None = None
