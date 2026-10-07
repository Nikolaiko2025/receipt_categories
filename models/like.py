from sqlalchemy import Column, Integer, Sequence
from db.base import Base


class Like(Base):
    """Лайк пользователя.

    Первичный ключ — все три колонки: id_user, id_receipt_category, id_like.
    Внешних ключей в таблице нет: связь с users и с receipt_categories
    описана отношением ORM (см. models/receipt_categories.py), а не ограничением БД.
    """

    __tablename__ = "likes"

    id_user = Column(Integer, primary_key=True)
    id_receipt_category = Column(Integer, primary_key=True)
    id_like = Column(Integer, Sequence("likes_id_like_seq"), primary_key=True)
