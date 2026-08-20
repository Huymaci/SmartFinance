from calendar import monthrange
from datetime import date, datetime, timedelta
from statistics import median

from sqlalchemy import func, select

from app.extensions import db
from app.models import Account, Alert, Budget, Transaction

from .budgets import spent_by_category
from .common import ValidationError


def _previous_month(value):
    return (value.replace(day=1) - timedelta(days=1)).replace(day=1)


def historical_weight(user_id, category_id, today):
    fractions = []
    cursor = _previous_month(today)
    for _ in range(6):
        next_month = date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)
        total = db.session.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.direction == "OUT", Transaction.category_id == category_id,
            Transaction.posted_at >= cursor, Transaction.posted_at < next_month,
            Transaction.account.has(Account.ledger.has(user_id=user_id)),
        )) or 0
        cutoff = datetime(cursor.year, cursor.month, min(today.day, monthrange(cursor.year, cursor.month)[1])) + timedelta(days=1)
        cumulative = db.session.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.direction == "OUT", Transaction.category_id == category_id,
            Transaction.posted_at >= cursor, Transaction.posted_at < cutoff,
            Transaction.account.has(Account.ledger.has(user_id=user_id)),
        )) or 0
        if total > 0:
            fractions.append(cumulative / total)
        cursor = _previous_month(cursor)
    if len(fractions) >= 3:
        return median(fractions), "historical"
    return today.day / monthrange(today.year, today.month)[1], "linear"


def _emit(user_id, category_id, kind, severity, dedup_key, explanation, action, now):
    recent = db.session.scalar(select(Alert.id).where(Alert.user_id == user_id, Alert.dedup_key == dedup_key, Alert.triggered_at >= now - timedelta(hours=72)))
    if recent:
        return False
    db.session.add(Alert(user_id=user_id, category_id=category_id, kind=kind, severity=severity, dedup_key=dedup_key, explanation=explanation, suggested_action=action, triggered_at=now))
    return True


def recompute(user_id, today=None):
    today = today or date.today()
    now = datetime.combine(today, datetime.min.time())
    budgets = list(db.session.scalars(select(Budget).where(Budget.user_id == user_id, Budget.month == today.replace(day=1))))
    spent = spent_by_category(user_id, today.replace(day=1))
    created = 0
    for budget in budgets:
        actual = spent.get(budget.category_id, 0)
        if budget.amount <= 0:
            continue
        ratio = actual / budget.amount
        for threshold, severity in ((0.8, "WARNING"), (1.0, "CRITICAL")):
            if ratio >= threshold:
                pct = int(threshold * 100)
                created += _emit(user_id, budget.category_id, "THRESHOLD", severity, f"threshold:{budget.category_id}:{today:%Y-%m}:{pct}", f"Chi tiêu đã đạt {int(ratio * 100)}% ngân sách; ngưỡng {pct}% đã bị vượt.", "Giảm hoặc hoãn một khoản chi không thiết yếu trong tháng này.", now)
        weight, method = historical_weight(user_id, budget.category_id, today)
        projected = actual / weight if weight > 0 else actual
        if projected > budget.amount * 1.05:
            created += _emit(user_id, budget.category_id, "BURN_RATE", "WARNING", f"burn:{budget.category_id}:{today:%Y-%m}", f"Theo nhịp chi tiêu {method}, cuối tháng dự kiến {round(projected):,} VND, vượt ngân sách hơn 5%.", "Đặt giới hạn chi tiêu theo ngày cho phần còn lại của tháng.", now)
    db.session.commit()
    return created


def list_alerts(user_id):
    return list(db.session.scalars(select(Alert).where(Alert.user_id == user_id).order_by(Alert.triggered_at.desc(), Alert.id.desc())))


def set_status(user_id, alert_id, status):
    if status not in {"READ", "DISMISSED"}:
        raise ValidationError("Trạng thái phải là READ hoặc DISMISSED")
    alert = db.session.scalar(select(Alert).where(Alert.id == alert_id, Alert.user_id == user_id))
    if not alert:
        from flask import abort
        abort(404)
    alert.status = status
    db.session.commit()
    return alert
