from sqlalchemy import Column, Date, DateTime, Integer, Numeric, String, Text
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

    likes = relationship("Like", backref="receipt_category")