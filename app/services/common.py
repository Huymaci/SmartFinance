import re
from datetime import datetime

from flask import abort

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class ValidationError(ValueError):
    pass


def require_fields(data, *fields):
    missing = [field for field in fields if data.get(field) in (None, "")]
    if missing:
        raise ValidationError("Thiếu trường: " + ", ".join(missing))


def parse_date(value, field="date"):
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} phải có định dạng YYYY-MM-DD") from exc


def owned_or_404(value):
    if value is None:
        abort(404)
    return value
