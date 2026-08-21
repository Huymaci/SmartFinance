from datetime import date, datetime

import pytest

from app import create_app
from app.extensions import db
from app.models import Account, Category, Ledger, Transaction, User
from config import TestConfig
from scripts.seed_mock import _clear_demo_data, _month_starts, generate_synthetic_rows


def test_synthetic_generator_is_deterministic_and_splits_all_rows():
    first = generate_synthetic_rows(101, date(2026, 1, 1), date(2026, 1, 31), seed=42)
    second = generate_synthetic_rows(101, date(2026, 1, 1), date(2026, 1, 31), seed=42)

    assert first == second
    assert {bank: len(rows) for bank, rows in first.items()} == {"BIDV": 97, "MB": 3, "VPB": 1}
    assert sum(map(len, first.values())) == 101

    for rows in first.values():
        assert len({row.ref_no for row in rows}) == len(rows)
        assert all(date(2026, 1, 1) <= row.posted_at.date() <= date(2026, 1, 31) for row in rows)
        assert all(row.signed_amount and abs(row.signed_amount) % 1_000 == 0 for row in rows)
        assert all(row.category_name for row in rows)

    mb_salary = [row for row in first["MB"] if row.category_name == "Thu nhập"]
    bidv_rent = [row for row in first["BIDV"] if row.category_name == "Nhà ở"]
    mb_transfers = [row for row in first["MB"] if row.category_name == "Chuyển khoản"]
    bidv_transfer = [row for row in first["BIDV"] if row.category_name == "Chuyển khoản"]
    assert len(mb_salary) == len(bidv_rent) == len(bidv_transfer) == 1
    assert 25_000_000 <= mb_salary[0].signed_amount <= 30_000_000
    assert bidv_rent[0].signed_amount == -3_000_000
    assert len(mb_transfers) == 2 and all(row.signed_amount < 0 for row in mb_transfers)
    assert bidv_transfer[0].signed_amount == -next(row.signed_amount for row in mb_transfers if row.ref_no == bidv_transfer[0].ref_no)
    assert len(first["VPB"]) == 1 and first["VPB"][0].signed_amount > 0
    assert first["VPB"][0].signed_amount == -next(row.signed_amount for row in mb_transfers if row.ref_no == first["VPB"][0].ref_no)
    assert mb_salary[0].signed_amount + sum(row.signed_amount for row in mb_transfers) == 2_000_000
    bidv_expense = -sum(row.signed_amount for row in first["BIDV"] if row.signed_amount < 0)
    assert 500_000 <= bidv_transfer[0].signed_amount - bidv_expense <= 1_500_000
    assert all(row.signed_amount < 0 for row in first["BIDV"] if row.category_name != "Chuyển khoản")
    assert all(row.posted_at.day >= 7 for row in first["BIDV"] if row.category_name != "Chuyển khoản")
    assert all("TIET KIEM" not in row.description.upper() for row in first["VPB"])


def test_synthetic_generator_changes_with_seed_and_validates_arguments():
    first = generate_synthetic_rows(10, date(2026, 1, 1), date(2026, 1, 31), seed=1)
    second = generate_synthetic_rows(10, date(2026, 1, 1), date(2026, 1, 31), seed=2)
    assert first != second

    with pytest.raises(ValueError):
        generate_synthetic_rows(-1)
    with pytest.raises(ValueError):
        generate_synthetic_rows(1, date(2026, 2, 1), date(2026, 1, 1))
    with pytest.raises(ValueError):
        generate_synthetic_rows(5, date(2026, 1, 1), date(2026, 1, 31))


def test_month_starts_cross_year_boundary():
    assert list(_month_starts(date(2025, 11, 20), date(2026, 2, 3))) == [
        date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1),
    ]


def test_clear_demo_data_preserves_non_mock_account_and_its_transactions():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        user = User(email="demo@example.com", password_hash="hash", full_name="Demo", date_of_birth=date(1990, 1, 1), role="USER")
        user.ledger = Ledger()
        category = Category(name="Khác", nature="DISCRETIONARY")
        db.session.add_all([user, category])
        db.session.flush()
        mb = Account(ledger_id=user.ledger.id, name="MB", type="BANK", bank_code="MB", last_four="2001", opening_balance=0)
        other = Account(ledger_id=user.ledger.id, name="NAB thủ công", type="BANK", bank_code="NAB", last_four="1234", opening_balance=0)
        db.session.add_all([mb, other])
        db.session.flush()
        db.session.add_all([
            Transaction(account_id=mb.id, category_id=category.id, posted_at=datetime(2026, 1, 1), amount=10_000, direction="OUT"),
            Transaction(account_id=other.id, category_id=category.id, posted_at=datetime(2026, 1, 1), amount=20_000, direction="OUT"),
        ])
        db.session.commit()

        _clear_demo_data(user)
        db.session.commit()

        assert db.session.query(Account).filter_by(bank_code="MB").count() == 0
        assert db.session.query(Account).filter_by(bank_code="NAB").count() == 1
        assert db.session.query(Transaction).join(Account).filter(Account.bank_code == "NAB").count() == 1
        db.session.remove()
        db.drop_all()
