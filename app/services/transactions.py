from app.extensions import db
from app.models import Transaction
from app.repositories import AccountRepository, CategoryRepository, TransactionRepository

from .common import ValidationError, owned_or_404, parse_date, require_fields


def _values(user_id, data):
    require_fields(data, "date", "amount", "direction", "account_id", "category_id")
    direction = data["direction"].upper()
    if direction not in {"IN", "OUT"}:
        raise ValidationError("direction phải là IN hoặc OUT")
    try:
        amount = int(data["amount"])
        account_id = int(data["account_id"])
        category_id = int(data["category_id"])
    except (TypeError, ValueError) as exc:
        raise ValidationError("amount, account_id và category_id phải là số nguyên") from exc
    if amount <= 0:
        raise ValidationError("Số tiền phải lớn hơn 0")
    owned_or_404(AccountRepository.owned(account_id, user_id, include_archived=False))
    owned_or_404(CategoryRepository.available(category_id, user_id))
    return {"posted_at": parse_date(data["date"]), "amount": amount, "direction": direction, "account_id": account_id, "category_id": category_id, "description": str(data.get("description", "")).strip(), "source": "MANUAL"}


def create(user, data):
    transaction = Transaction(**_values(user.id, data))
    db.session.add(transaction)
    db.session.commit()
    return transaction


def update(user, transaction_id, data):
    transaction = owned_or_404(TransactionRepository.owned(transaction_id, user.id))
    for key, value in _values(user.id, data).items():
        setattr(transaction, key, value)
    db.session.commit()
    return transaction


def delete(user, transaction_id):
    transaction = owned_or_404(TransactionRepository.owned(transaction_id, user.id))
    db.session.delete(transaction)
    db.session.commit()
