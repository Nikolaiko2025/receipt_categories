from sqlalchemy import Column, Integer, String
from db.base import Base


class User(Base):
    __tablename__ = "users"

    id_user = Column(Integer, primary_key=True)
    # логин уникален: проверяется при регистрации и уникальным индексом в БД
    username = Column(String(50), nullable=False, unique=True)
    password = Column(String(255), nullable=False)
