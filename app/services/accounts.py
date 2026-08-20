from app.extensions import db
from app.models import Account
from app.repositories import AccountRepository

from .common import ValidationError, owned_or_404, require_fields


def _values(data):
    require_fields(data, "name", "type", "opening_balance")
    account_type = data["type"].upper()
    if account_type not in {"CASH", "BANK"}:
        raise ValidationError("Loại tài khoản phải là CASH hoặc BANK")
    try:
        balance = int(data["opening_balance"])
    except (TypeError, ValueError) as exc:
        raise ValidationError("Số dư đầu kỳ phải là số nguyên VND") from exc
    last_four = data.get("last_four")
    if account_type == "BANK" and (not last_four or len(last_four) != 4 or not last_four.isdigit()):
        raise ValidationError("Tài khoản ngân hàng chỉ lưu đúng 4 số cuối")
    if any(key in data for key in ("account_number", "credentials", "password", "otp")):
        raise ValidationError("Không được gửi số tài khoản đầy đủ hoặc thông tin xác thực ngân hàng")
    return {"name": data["name"].strip(), "type": account_type, "opening_balance": balance, "bank_code": data.get("bank_code"), "last_four": last_four if account_type == "BANK" else None}


def create(user, data):
    account = Account(ledger_id=user.ledger.id, **_values(data))
    db.session.add(account)
    db.session.commit()
    return account


def update(user, account_id, data):
    account = owned_or_404(AccountRepository.owned(account_id, user.id))
    for key, value in _values(data).items():
        setattr(account, key, value)
    db.session.commit()
    return account


def archive(user, account_id):
    account = owned_or_404(AccountRepository.owned(account_id, user.id))
    account.archived = True
    db.session.commit()


def restore(user, account_id):
    account = owned_or_404(AccountRepository.owned(account_id, user.id))
    account.archived = False
    db.session.commit()
    return account
