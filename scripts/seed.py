import json
import os
from datetime import date

from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import CategorizationRule, Category, ImportTemplate, User

CATEGORIES = {
    "Thiết yếu": [("Nhà ở", "COMMITTED"), ("Học phí", "COMMITTED"), ("Điện nước", "SEMI_FIXED")],
    "Linh hoạt": [("Ăn uống", "DISCRETIONARY"), ("Mua sắm", "DISCRETIONARY"), ("Nhiên liệu", "SEMI_FIXED")],
}

TEMPLATES = [
    ("VCB", "Vietcombank - số tiền có dấu", {"header_rows": 1, "date": 0, "description": 1, "amount": 2, "ref_no": 3, "date_format": "%d/%m/%Y"}),
    ("TCB", "Techcombank - ghi nợ/ghi có", {"header_rows": 1, "date": 0, "description": 1, "debit": 2, "credit": 3, "ref_no": 4, "date_format": "%d/%m/%Y"}),
    ("MB", "MB Bank - ghi nợ/ghi có", {"header_rows": 1, "date": 0, "ref_no": 1, "description": 2, "debit": 3, "credit": 4, "date_format": "%d/%m/%Y"}),
]


def seed():
    for parent_name, children in CATEGORIES.items():
        parent = Category.query.filter_by(name=parent_name, owner_id=None).first()
        if not parent:
            parent = Category(name=parent_name, nature=None)
            db.session.add(parent)
            db.session.flush()
        for name, nature in children:
            if not Category.query.filter_by(name=name, owner_id=None).first():
                db.session.add(Category(name=name, nature=nature, parent_id=parent.id))
    for bank_code, name, mapping in TEMPLATES:
        if not ImportTemplate.query.filter_by(bank_code=bank_code, name=name).first():
            db.session.add(ImportTemplate(bank_code=bank_code, name=name, mapping_json=json.dumps(mapping), active=True))
    dining = Category.query.filter_by(name="Ăn uống", owner_id=None).first()
    shopping = Category.query.filter_by(name="Mua sắm", owner_id=None).first()
    for priority, pattern, category in ((10, r"highlands|coffee|cafe", dining), (20, r"shopee|lazada|tiki", shopping)):
        if category and not CategorizationRule.query.filter_by(priority=priority).first():
            db.session.add(CategorizationRule(pattern=pattern, category_id=category.id, priority=priority, active=True))
    admin_email = os.getenv("ADMIN_EMAIL", "admin@smartfinance.local").lower()
    if not User.query.filter_by(email=admin_email).first():
        admin_password = os.getenv("ADMIN_PASSWORD")
        if not admin_password:
            raise RuntimeError("ADMIN_PASSWORD phải được đặt trong môi trường khi seed")
        db.session.add(User(email=admin_email, full_name="Quản trị hệ thống", date_of_birth=date(1990, 1, 1), consent=False, role="ADMIN", password_hash=generate_password_hash(admin_password, method="pbkdf2:sha256:600000")))
    db.session.commit()


if __name__ == "__main__":
    application = create_app()
    with application.app_context():
        seed()
