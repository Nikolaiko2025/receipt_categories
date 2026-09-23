from sqlalchemy import Column, ForeignKey, Integer
from db.base import Base


class Like(Base):
    __tablename__ = "likes"

    id_user = Column(Integer, ForeignKey("users.id_user"), primary_key=True)
    id_receipt_category = Column(Integer, ForeignKey("receipt_categories.id_receipt_category"), primary_key=True)