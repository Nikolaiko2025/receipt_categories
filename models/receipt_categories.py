from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship
from db.base import Base


class Receipt_categories(Base):
    __tablename__ = "receipt_categories"

    id_receipt_category = Column(Integer, primary_key=True)
    title = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False)
    category = Column(String(20), nullable=False)
    category_display = Column(String(50), nullable=False)
    amount = Column(Numeric(15, 2))
    date = Column(Date)
    description = Column(Text)
    status = Column(String(11), nullable=False)
    image_url = Column(String(255), nullable=False)
    video_url = Column(String(255), nullable=False)
    date_created = Column(DateTime, nullable=False)
    creator = Column(String(50), nullable=False)
    date_formed = Column(DateTime)
    # система: кто создал (FK на пользователя) и когда услуга завершена (удалена)
    id_user = Column(Integer, ForeignKey("users.id_user"), nullable=False)
    date_completed = Column(DateTime)

    # в таблице likes внешнего ключа нет, поэтому соединение указываем явно
    likes = relationship(
        "Like",
        primaryjoin="Receipt_categories.id_receipt_category == foreign(Like.id_receipt_category)",
        backref="receipt_category",
    )
