from sqlalchemy import select

from app.extensions import db
from app.models import Account, Category, Transaction, User


class UserRepository:
    @staticmethod
    def by_email(email):
        return db.session.scalar(select(User).where(User.email == email.lower()))

    @staticmethod
    def add(user):
        db.session.add(user)
        db.session.flush()
        return user


class AccountRepository:
    @staticmethod
    def owned(account_id, user_id, include_archived=True):
        query = select(Account).where(
            Account.id == account_id,
            Account.ledger.has(user_id=user_id),
        )
        if not include_archived:
            query = query.where(Account.archived.is_(False))
        return db.session.scalar(query)

    @staticmethod
    def list_for(user_id):
        return list(db.session.scalars(select(Account).where(Account.ledger.has(user_id=user_id)).order_by(Account.id)))


class TransactionRepository:
    @staticmethod
    def owned(transaction_id, user_id):
        return db.session.scalar(
            select(Transaction).where(
                Transaction.id == transaction_id,
                Transaction.account.has(Account.ledger.has(user_id=user_id)),
            )
        )

    @staticmethod
    def search(user_id, *, date_from=None, date_to=None, account_id=None, category_id=None, direction=None, page=1, per_page=20):
        query = select(Transaction).where(Transaction.account.has(Account.ledger.has(user_id=user_id)))
        if date_from:
            query = query.where(Transaction.posted_at >= date_from)
        if date_to:
            query = query.where(Transaction.posted_at <= date_to)
        if account_id:
            query = query.where(Transaction.account_id == account_id)
        if category_id:
            query = query.where(Transaction.category_id == category_id)
        if direction:
            query = query.where(Transaction.direction == direction)
        return db.paginate(query.order_by(Transaction.posted_at.desc(), Transaction.id.desc()), page=page, per_page=per_page, error_out=False)


class CategoryRepository:
    @staticmethod
    def available(category_id, user_id):
        return db.session.scalar(select(Category).where(Category.id == category_id, (Category.owner_id.is_(None)) | (Category.owner_id == user_id)))
