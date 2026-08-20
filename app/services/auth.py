import re
from datetime import date, datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import Ledger, User, utcnow
from app.repositories import UserRepository

from .common import EMAIL_RE, ValidationError, require_fields


def validate_password(password):
    classes = sum(bool(re.search(pattern, password)) for pattern in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if len(password) < 10 or classes < 3:
        raise ValidationError("Mật khẩu cần ít nhất 10 ký tự và 3 nhóm ký tự")


def register(data):
    require_fields(data, "email", "password", "full_name", "date_of_birth")
    email = data["email"].strip().lower()
    if not EMAIL_RE.fullmatch(email):
        raise ValidationError("Email không hợp lệ")
    validate_password(data["password"])
    try:
        birth_date = datetime.strptime(data["date_of_birth"], "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValidationError("Ngày sinh phải có định dạng YYYY-MM-DD") from exc
    today = date.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    if age < 18:
        raise ValidationError("Người dùng phải đủ 18 tuổi")
    if UserRepository.by_email(email):
        raise ValidationError("Email đã tồn tại")
    user = User(
        email=email,
        full_name=data["full_name"].strip(),
        date_of_birth=birth_date,
        consent=data.get("consent") is True,
        password_hash=generate_password_hash(data["password"], method="pbkdf2:sha256:600000"),
    )
    UserRepository.add(user)
    user.ledger = Ledger()
    db.session.commit()
    return user


def authenticate(email, password):
    user = UserRepository.by_email((email or "").strip().lower())
    now = utcnow()
    if user and user.locked_until and user.locked_until > now:
        raise ValidationError("Tài khoản đang tạm khóa")
    if not user or not check_password_hash(user.password_hash, password or ""):
        if user:
            user.failed_logins += 1
            if user.failed_logins >= 5:
                user.locked_until = now + timedelta(minutes=15)
            db.session.commit()
        raise ValidationError("Email hoặc mật khẩu không đúng")
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    db.session.commit()
    return user


def change_password(user, current_password, new_password):
    if not check_password_hash(user.password_hash, current_password or ""):
        raise ValidationError("Mật khẩu hiện tại không đúng")
    validate_password(new_password or "")
    user.password_hash = generate_password_hash(new_password, method="pbkdf2:sha256:600000")
    db.session.commit()
