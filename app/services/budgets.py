from datetime import date, datetime

from sqlalchemy import func, select

from app.extensions import db
from app.models import Account, Budget, Category, Transaction
from app.repositories import CategoryRepository

from .common import ValidationError, owned_or_404


def month_start(value):
    try:
        parsed = datetime.strptime(value, "%Y-%m").date() if isinstance(value, str) else value
        return parsed.replace(day=1)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Tháng phải có định dạng YYYY-MM") from exc


def set_budget(user, data):
    month = month_start(data.get("month"))
    try:
        category_id, amount = int(data.get("category_id")), int(data.get("amount"))
    except (TypeError, ValueError) as exc:
        raise ValidationError("category_id và amount phải là số nguyên") from exc
    if amount < 0:
        raise ValidationError("Ngân sách không được âm")
    owned_or_404(CategoryRepository.available(category_id, user.id))
    budget = db.session.scalar(select(Budget).where(Budget.user_id == user.id, Budget.category_id == category_id, Budget.month == month))
    if budget:
        budget.amount = amount
    else:
        budget = Budget(user_id=user.id, category_id=category_id, month=month, amount=amount)
        db.session.add(budget)
    db.session.commit()
    return budget


def list_budgets(user_id, month):
    return list(db.session.scalars(select(Budget).where(Budget.user_id == user_id, Budget.month == month_start(month)).order_by(Budget.category_id)))


def copy_previous(user, target_month):
    target = month_start(target_month)
    previous = (target.replace(day=1) - __import__("datetime").timedelta(days=1)).replace(day=1)
    source = list_budgets(user.id, previous)
    count = 0
    for item in source:
        existing = db.session.scalar(select(Budget).where(Budget.user_id == user.id, Budget.category_id == item.category_id, Budget.month == target))
        if not existing:
            db.session.add(Budget(user_id=user.id, category_id=item.category_id, month=target, amount=item.amount))
            count += 1
    db.session.commit()
    return count


def spent_by_category(user_id, month):
    start = month_start(month)
    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)
    rows = db.session.execute(select(Transaction.category_id, func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.direction == "OUT", Transaction.posted_at >= start, Transaction.posted_at < end,
        Transaction.account.has(Account.ledger.has(user_id=user_id)),
    ).group_by(Transaction.category_id)).all()
    return dict(rows)


def safe_to_spend(user_id, month=None):
    target = month_start(month or date.today().replace(day=1))
    balance = db.session.scalar(select(func.coalesce(func.sum(Account.opening_balance), 0)).where(Account.ledger.has(user_id=user_id))) or 0
    directions = db.session.execute(select(Transaction.direction, func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.account.has(Account.ledger.has(user_id=user_id))).group_by(Transaction.direction)).all()
    totals = dict(directions)
    balance += totals.get("IN", 0) - totals.get("OUT", 0)
    spent = spent_by_category(user_id, target)
    reserved = 0
    for budget, nature in db.session.execute(select(Budget, Category.nature).join(Category).where(Budget.user_id == user_id, Budget.month == target)):
        if nature in {"COMMITTED", "SEMI_FIXED"}:
            reserved += max(0, budget.amount - spent.get(budget.category_id, 0))
    return balance - reserved
