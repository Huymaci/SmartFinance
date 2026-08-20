import csv
import hashlib
import io
import json
import secrets
import zipfile

from sqlalchemy import delete, select

from app.extensions import db
from app.models import Account, Alert, AuditLog, Budget, Category, ImportBatch, ImportError, Ledger, Transaction


def export_data(user):
    accounts = user.ledger.accounts
    account_ids = {account.id for account in accounts}
    transactions = list(db.session.query(Transaction).filter(Transaction.account_id.in_(account_ids))) if account_ids else []
    categories = list(db.session.scalars(select(Category).where(Category.owner_id == user.id)))
    budgets = list(db.session.scalars(select(Budget).where(Budget.user_id == user.id)))
    alerts = list(db.session.scalars(select(Alert).where(Alert.user_id == user.id)))
    imports = list(db.session.scalars(select(ImportBatch).where(ImportBatch.user_id == user.id)))
    import_ids = [item.id for item in imports]
    import_errors = list(db.session.scalars(select(ImportError).where(ImportError.batch_id.in_(import_ids)))) if import_ids else []
    audit_logs = list(db.session.scalars(select(AuditLog).where(AuditLog.user_id == user.id)))
    payload = {
        "profile": {"email": user.email, "full_name": user.full_name, "date_of_birth": user.date_of_birth.isoformat(), "consent": user.consent},
        "accounts": [{"id": a.id, "name": a.name, "type": a.type, "opening_balance": a.opening_balance, "bank_code": a.bank_code, "last_four": a.last_four, "archived": a.archived} for a in accounts],
        "transactions": [{"id": t.id, "date": t.posted_at.date().isoformat(), "amount": t.amount, "direction": t.direction, "account_id": t.account_id, "category_id": t.category_id, "description": t.description} for t in transactions],
        "custom_categories": [{"id": x.id, "parent_id": x.parent_id, "name": x.name, "nature": x.nature} for x in categories],
        "budgets": [{"id": x.id, "category_id": x.category_id, "month": x.month.isoformat(), "amount": x.amount} for x in budgets],
        "alerts": [{"id": x.id, "category_id": x.category_id, "kind": x.kind, "severity": x.severity, "explanation": x.explanation, "suggested_action": x.suggested_action, "status": x.status, "triggered_at": x.triggered_at.isoformat()} for x in alerts],
        "imports": [{"id": x.id, "account_id": x.account_id, "template_id": x.template_id, "filename": x.filename, "status": x.status, "created_at": x.created_at.isoformat()} for x in imports],
        "import_errors": [{"batch_id": x.batch_id, "row_number": x.row_number, "reason": x.reason} for x in import_errors],
        "audit_logs": [{"action": x.action, "created_at": x.created_at.isoformat()} for x in audit_logs],
    }
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(csv_buffer, fieldnames=["id", "date", "amount", "direction", "account_id", "category_id", "description"])
    writer.writeheader()
    writer.writerows(payload["transactions"])
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("smartfinance.json", json.dumps(payload, ensure_ascii=False, indent=2))
        bundle.writestr("transactions.csv", csv_buffer.getvalue())
    archive.seek(0)
    return archive


def delete_account(user):
    # Explicit order makes erasure verifiable even before relying on InnoDB cascades.
    account_ids = list(db.session.scalars(select(Account.id).where(Account.ledger.has(user_id=user.id))))
    batch_ids = list(db.session.scalars(select(ImportBatch.id).where(ImportBatch.user_id == user.id)))
    if batch_ids:
        db.session.execute(delete(ImportError).where(ImportError.batch_id.in_(batch_ids)))
    if account_ids:
        db.session.execute(delete(Transaction).where(Transaction.account_id.in_(account_ids)))
    db.session.execute(delete(ImportBatch).where(ImportBatch.user_id == user.id))
    db.session.execute(delete(Alert).where(Alert.user_id == user.id))
    db.session.execute(delete(Budget).where(Budget.user_id == user.id))
    db.session.execute(delete(Category).where(Category.owner_id == user.id))
    db.session.execute(delete(AuditLog).where(AuditLog.user_id == user.id))
    if account_ids:
        db.session.execute(delete(Account).where(Account.id.in_(account_ids)))
    db.session.execute(delete(Ledger).where(Ledger.user_id == user.id))
    salt = secrets.token_bytes(16)
    deleted_email_hash = hashlib.sha256(salt + user.email.encode("utf-8")).hexdigest()
    db.session.delete(user)
    db.session.flush()
    db.session.add(AuditLog(user_id=None, action=f"ACCOUNT_DELETED:{salt.hex()}:{deleted_email_hash}"))
    db.session.commit()
