from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from app.extensions import db
from app.models import Account, Budget, Category, Transaction

from .budgets import month_start, safe_to_spend, spent_by_category
from .common import ValidationError


def _next_month(value):
    return date(value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1)


def dashboard(user_id, month=None):
    start = month_start(month or date.today().replace(day=1))
    end = _next_month(start)
    rows = db.session.execute(select(Transaction.direction, func.coalesce(func.sum(Transaction.amount), 0)).join(Category).where(
        Transaction.posted_at >= start, Transaction.posted_at < end,
        Transaction.account.has(Account.ledger.has(user_id=user_id)),
        Category.name != "Chuyển khoản",
    ).group_by(Transaction.direction)).all()
    totals = dict(rows)
    spent = spent_by_category(user_id, start)
    progress = []
    for budget, name in db.session.execute(select(Budget, Category.name).join(Category).where(Budget.user_id == user_id, Budget.month == start)):
        actual = spent.get(budget.category_id, 0)
        ratio = actual / budget.amount if budget.amount else 0
        status = "GREEN" if ratio < 0.8 else "AMBER" if ratio < 1 else "RED"
        label = "Trong kế hoạch" if status == "GREEN" else "Sắp chạm ngân sách" if status == "AMBER" else "Vượt ngân sách"
        progress.append({"category_id": budget.category_id, "category": name, "budget": budget.amount, "spent": actual, "percent": round(ratio * 100, 1), "status": status, "label": label})
    income, expense = totals.get("IN", 0), totals.get("OUT", 0)
    return {"income": income, "expense": expense, "net": income - expense, "safe_to_spend": safe_to_spend(user_id, start), "budget_progress": progress}


def breakdown(user_id, date_from, date_to):
    try:
        start, end = datetime.strptime(date_from, "%Y-%m-%d"), datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
    except (TypeError, ValueError) as exc:
        raise ValidationError("date_from/date_to phải có định dạng YYYY-MM-DD") from exc
    rows = db.session.execute(select(Category.id, Category.name, func.sum(Transaction.amount)).join(Transaction).where(
        Transaction.direction == "OUT", Transaction.posted_at >= start, Transaction.posted_at < end,
        Transaction.account.has(Account.ledger.has(user_id=user_id)),
        Category.name != "Chuyển khoản",
    ).group_by(Category.id, Category.name).order_by(func.sum(Transaction.amount).desc())).all()
    return [{"category_id": item[0], "category": item[1], "amount": item[2]} for item in rows]


def trend(user_id, through=None):
    cursor = month_start(through or date.today().replace(day=1))
    months = []
    for _ in range(12):
        months.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    months.reverse()
    result = []
    for start in months:
        end = _next_month(start)
        rows = dict(db.session.execute(select(Transaction.direction, func.coalesce(func.sum(Transaction.amount), 0)).join(Category).where(
            Transaction.posted_at >= start, Transaction.posted_at < end,
            Transaction.account.has(Account.ledger.has(user_id=user_id)),
            Category.name != "Chuyển khoản",
        ).group_by(Transaction.direction)).all())
        result.append({"month": start.strftime("%Y-%m"), "income": rows.get("IN", 0), "expense": rows.get("OUT", 0)})
    return result
