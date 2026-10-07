"""Слой доступа к данным — Repository (методичка, п. 1.7 «Модификация Repository»).

Здесь собраны все ORM-запросы к PostgreSQL. Handler (api/rest.py) разбирает
HTTP-запрос, валидирует данные и принимает бизнес-решения (какой статус
выставить, чья услуга), а чтением/записью БД занимается только Repository.

Защита от краевых случаев: ид вне диапазона типа integer в БД не существует,
поэтому такие ид сразу считаются ненайденными — иначе asyncpg вернёт
ошибку 500 «value out of range for type integer».
"""
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import STATUS_DRAFT, STATUS_PUBLISHED
from models.like import Like
from models.receipt_categories import Receipt_categories
from models.user import User

INT4_MIN = -2147483648
INT4_MAX = 2147483647


def _valid_id(value: int) -> bool:
    """Ид существует только в пределах колонки integer таблицы БД."""
    return INT4_MIN <= value <= INT4_MAX


class Repository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------ users

    async def get_user_by_login(self, username: str) -> User | None:
        result = await self.db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def create_user(self, username: str, password: str) -> User:
        user = User(username=username, password=password)
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    # ---------------------------------------------------------- receipt_categories

    async def list_receipts(
        self,
        *,
        type: str | None = None,
        category: str | None = None,
        title: str | None = None,
        min_amount: float | None = None,
        max_amount: float | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        expense: bool | None = None,
        mine: bool | None = None,
        user_id: int | None = None,
    ) -> list[Receipt_categories]:
        """Опубликованные услуги с фильтрацией (WHERE выполняет СУБД)."""
        stmt = select(Receipt_categories).where(
            Receipt_categories.status == STATUS_PUBLISHED
        )

        if type:
            stmt = stmt.where(Receipt_categories.type == type)
        if category:
            stmt = stmt.where(Receipt_categories.category == category)
        if title:
            stmt = stmt.where(Receipt_categories.title.ilike(f"%{title}%"))
        if min_amount is not None:
            stmt = stmt.where(Receipt_categories.amount >= min_amount)
        if max_amount is not None:
            stmt = stmt.where(Receipt_categories.amount <= max_amount)
        if date_from is not None:
            stmt = stmt.where(Receipt_categories.date >= date_from)
        if date_to is not None:
            stmt = stmt.where(Receipt_categories.date <= date_to)
        if expense is True:
            stmt = stmt.where(
                or_(Receipt_categories.amount < 0, Receipt_categories.amount.is_(None))
            )
        elif expense is False:
            stmt = stmt.where(Receipt_categories.amount >= 0)
        if mine is True and user_id is not None:
            stmt = stmt.where(Receipt_categories.id_user == user_id)
        elif mine is False and user_id is not None:
            stmt = stmt.where(Receipt_categories.id_user != user_id)

        stmt = stmt.order_by(Receipt_categories.id_receipt_category)
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_receipt(self, receipt_id: int) -> Receipt_categories | None:
        if not _valid_id(receipt_id):
            return None
        result = await self.db.execute(
            select(Receipt_categories).where(
                Receipt_categories.id_receipt_category == receipt_id
            )
        )
        return result.scalar_one_or_none()

    async def get_first_published(self) -> Receipt_categories | None:
        result = await self.db.execute(
            select(Receipt_categories)
            .where(Receipt_categories.status == STATUS_PUBLISHED)
            .order_by(Receipt_categories.id_receipt_category)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_next_published(self, after_id: int) -> Receipt_categories | None:
        """Следующая опубликованная услуга после указанного ида (LIMIT 1)."""
        if not _valid_id(after_id):
            return None
        result = await self.db.execute(
            select(Receipt_categories)
            .where(Receipt_categories.status == STATUS_PUBLISHED)
            .where(Receipt_categories.id_receipt_category > after_id)
            .order_by(Receipt_categories.id_receipt_category)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_draft(self, user_id: int) -> Receipt_categories | None:
        """Черновик пользователя — не более 1 записи."""
        result = await self.db.execute(
            select(Receipt_categories)
            .where(Receipt_categories.status == STATUS_DRAFT)
            .where(Receipt_categories.id_user == user_id)
            .order_by(Receipt_categories.id_receipt_category)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def save_receipt(self, receipt: Receipt_categories) -> Receipt_categories:
        """Фиксирует изменения услуги в БД (add/commit) и возвращает свежую строку."""
        self.db.add(receipt)
        await self.db.commit()
        await self.db.refresh(receipt)
        return receipt

    # ----------------------------------------------------------------- likes

    async def likes_meta(self, user_id: int, receipts: list[Receipt_categories]):
        """(сколько лайков у каждой услуги, лайкнул ли её текущий пользователь)."""
        ids = [receipt.id_receipt_category for receipt in receipts]
        if not ids:
            return {}, set()

        counts = dict(
            (
                await self.db.execute(
                    select(Like.id_receipt_category, func.count().label("cnt"))
                    .where(Like.id_receipt_category.in_(ids))
                    .group_by(Like.id_receipt_category)
                )
            ).all()
        )
        liked = set(
            (
                await self.db.execute(
                    select(Like.id_receipt_category)
                    .where(Like.id_user == user_id)
                    .where(Like.id_receipt_category.in_(ids))
                )
            ).scalars().all()
        )
        return counts, liked

    async def set_like(self, user_id: int, receipt_id: int, flag: int) -> None:
        """1 — поставить лайк, 0 — снять: перед вставкой проверяем, нет ли уже такого лайка."""
        result = await self.db.execute(
            select(Like)
            .where(Like.id_user == user_id)
            .where(Like.id_receipt_category == receipt_id)
        )
        like = result.scalar_one_or_none()

        if flag == 1:
            if like is None:
                self.db.add(Like(id_user=user_id, id_receipt_category=receipt_id))
        elif like is not None:
            await self.db.delete(like)

        await self.db.commit()
