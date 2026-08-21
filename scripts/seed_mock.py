"""Seed a realistic monthly cash flow using the supplied statements as patterns.

Usage (after migrations):
    python -m scripts.seed_mock --replace-demo-data

The command is idempotent. MB receives salary, funds BIDV for spending, and
moves retained cash to a normal VPBank payment account (not a savings product).
"""

import argparse
import csv
import hashlib
import os
import random
import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import delete, select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import Account, Alert, Budget, Category, ImportBatch, ImportError, Ledger, Transaction, User
from app.services.imports import dedup_key

DEFAULT_SOURCE_DIR = Path(r"D:\.Giả lập dữ liệu")
MOCK_EMAIL = "demo@smartexpense.local"
MOCK_PASSWORD = "SmartExpenseMock1!"
# The default reaches the 20,000-transaction dataset required by NFR-08.
DEFAULT_SYNTHETIC_COUNT = 20_000
DEFAULT_RANDOM_SEED = 20260820
DEFAULT_START_DATE = date(2024, 1, 1)
DEFAULT_END_DATE = date(2026, 8, 19)


@dataclass(frozen=True)
class StatementRow:
    posted_at: datetime
    signed_amount: int
    description: str
    ref_no: str
    category_name: str | None = None


CATEGORY_DEFINITIONS = (
    ("Thu nhập", "COMMITTED"),
    ("Nhà ở", "COMMITTED"),
    ("Điện nước", "SEMI_FIXED"),
    ("Ăn uống", "DISCRETIONARY"),
    ("Mua sắm", "DISCRETIONARY"),
    ("Di chuyển", "SEMI_FIXED"),
    ("Y tế", "SEMI_FIXED"),
    ("Học tập", "SEMI_FIXED"),
    ("Viễn thông", "SEMI_FIXED"),
    ("Chuyển khoản", "DISCRETIONARY"),
    ("Khác", "DISCRETIONARY"),
)


# category, weight and BIDV spending descriptions. Salary, rent and internal
# transfers are generated separately so their monthly cash-flow invariants hold.
SPENDING_PROFILES = (
    ("Ăn uống", 35, ("THANH TOAN AN UONG COM VAN PHONG", "PHO 24", "HIGHLANDS COFFEE", "BUN CHA HA NOI", "LOTTERIA")),
    ("Mua sắm", 22, ("LAZADA THANH TOAN DON HANG", "SHOPEE MUA SAM", "WINMART MUA THUC PHAM", "CO.OP FOOD", "CIRCLE K")),
    ("Di chuyển", 18, ("THANH TOAN GRAB", "THANH TOAN BE", "DI CHUYEN XANH SM", "HANOI METRO", "DO XANG PETROLIMEX")),
    ("Điện nước", 7, ("THANH TOAN TIEN DIEN EVNHANOI", "THANH TOAN TIEN NUOC HAWACOM")),
    ("Viễn thông", 5, ("THANH TOAN CUOC INTERNET VIETTEL", "NAP TIEN DIEN THOAI", "THANH TOAN FPT TELECOM")),
    ("Y tế", 4, ("NHA THUOC LONG CHAU", "KHAM BENH MEDLATEC", "THANH TOAN BENH VIEN")),
    ("Học tập", 5, ("CHI PHI HOC TAP", "FAHASA MUA SACH", "PHOTO NGUYEN PHONG IN TAI LIEU")),
    ("Khác", 4, ("THANH TOAN DICH VU", "PHI DICH VU NGAN HANG", "CHI TIEU KHAC")),
)

ACCOUNT_SPECS = {
    "MB": {"name": "MB Bank - Tài khoản nhận lương", "last_four": "2001", "opening_balance": 5_000_000},
    "BIDV": {"name": "BIDV - Tài khoản chi tiêu", "last_four": "4789", "opening_balance": 2_000_000},
    "VPB": {"name": "VPBank - Tài khoản giữ tiền", "last_four": "7537", "opening_balance": 0},
}


def _read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.reader(stream))


def _money(value):
    cleaned = re.sub(r"[^0-9+.-]", "", value or "")
    return int(round(float(cleaned))) if cleaned else 0


def parse_bidv(path):
    rows = _read_csv(path)
    result = []
    for row in rows[1:]:
        if len(row) < 5 or not row[0].strip():
            continue
        result.append(StatementRow(
            datetime.strptime(row[0].strip(), "%d/%m/%Y %H:%M:%S"),
            _money(row[2]), row[1].strip(), row[4].strip(),
        ))
    return result


def parse_mb(path):
    result = []
    for row in _read_csv(path):
        if len(row) < 12 or not row[1].strip().isdigit():
            continue
        debit, credit = _money(row[9]), _money(row[10])
        signed = credit - debit
        if signed:
            result.append(StatementRow(
                datetime.strptime(row[4].strip(), "%d/%m/%Y %H:%M"),
                signed, row[11].strip(), row[6].strip(),
            ))
    return result


def parse_vpbank(path):
    rows = _read_csv(path)
    header = next(i for i, row in enumerate(rows) if row and row[0].strip() == "Ngày")
    result = []
    for row in rows[header + 1:]:
        if len(row) < 7 or not row[0].strip():
            continue
        signed = _money(row[5])
        if signed:
            result.append(StatementRow(
                datetime.strptime(row[0].strip(), "%d/%m/%Y"),
                signed, row[3].strip(), row[4].strip(),
            ))
    return result


def _stable_seed(seed, *parts):
    value = "|".join((str(seed), *(str(part) for part in parts)))
    return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:8], "big")


def _synthetic_description(bank_code, base, direction, rng):
    account = f"{rng.randrange(1_000_000_000, 9_999_999_999)}"
    trace = f"{rng.randrange(100_000_000_000_000, 999_999_999_999_999)}"
    if bank_code == "BIDV":
        if direction == "IN":
            return f"TKThe :5020226080, tai TCB. {base}-{trace}"
        merchant = re.sub(r"[^A-Z0-9]+", "_", base.upper()).strip("_")[:40]
        return f"MB-TKThe {account}_{merchant}, tai BIDV. ND {base} -CTLNHIDO{trace}"
    if bank_code == "MB":
        return base.upper()
    return base.upper()


def _synthetic_ref(bank_code, posted_at, seed, index, rng):
    suffix = f"{seed % 1000:03d}{index:07d}"
    if bank_code == "BIDV":
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
        return rng.choice(("0552", "0831", "8681")) + "".join(rng.choice(alphabet) for _ in range(14)) + suffix[-3:]
    if bank_code == "MB":
        return f"FT{posted_at:%y}{posted_at.timetuple().tm_yday:03d}{suffix}"
    return f"FT{posted_at:%y%m%d}{suffix}"


def _monthly_amounts(total, count, rng, minimum=5_000):
    """Split a monthly spending target into positive, 1,000-VND amounts."""
    if count == 0:
        return []
    minimum_units = minimum // 1_000
    total_units = total // 1_000
    if total_units < count * minimum_units:
        raise ValueError("Số giao dịch quá lớn so với ngân sách chi tiêu tháng")
    remaining = total_units - count * minimum_units
    weights = [rng.expovariate(1) for _ in range(count)]
    weight_total = sum(weights)
    raw = [remaining * weight / weight_total for weight in weights]
    extra = [int(value) for value in raw]
    for index in sorted(range(count), key=lambda item: raw[item] - extra[item], reverse=True)[:remaining - sum(extra)]:
        extra[index] += 1
    return [(minimum_units + value) * 1_000 for value in extra]


def _recurring_rows(month, salary, bidv_transfer, vpbank_transfer):
    label = month.strftime("%m/%Y")
    salary_ref = f"SALARY-MB-{month:%Y%m}"
    rent_ref = f"RENT-MB-{month:%Y%m}"
    bidv_ref = f"XFER-MB-BIDV-{month:%Y%m}"
    vpbank_ref = f"XFER-MB-VPB-{month:%Y%m}"
    return {
        "MB": [
            StatementRow(datetime(month.year, month.month, 5, 9, 5), salary, f"LUONG THANG {label} CONG TY TNHH CONG NGHE VIET", salary_ref, "Thu nhập"),
            StatementRow(datetime(month.year, month.month, 6, 10, 20), -bidv_transfer, f"CHUYEN SANG BIDV DE CHI TIEU THANG {label}", bidv_ref, "Chuyển khoản"),
            StatementRow(datetime(month.year, month.month, 7, 10, 30), -vpbank_transfer, f"CHUYEN SANG VPBANK DE GIU TIEN THANG {label}", vpbank_ref, "Chuyển khoản"),
        ],
        "BIDV": [
            StatementRow(datetime(month.year, month.month, 6, 10, 20), bidv_transfer, f"NHAN TIEN TU MB DE CHI TIEU THANG {label}", bidv_ref, "Chuyển khoản"),
            StatementRow(datetime(month.year, month.month, 7, 8, 0), -3_000_000, f"THANH TOAN TIEN THUE NHA THANG {label}", rent_ref, "Nhà ở"),
        ],
        "VPB": [
            StatementRow(datetime(month.year, month.month, 7, 10, 30), vpbank_transfer, f"NHAN TIEN TU MB DE GIU TIEN THANG {label}", vpbank_ref, "Chuyển khoản"),
        ],
    }


def generate_synthetic_rows(total_count, start_date=DEFAULT_START_DATE, end_date=DEFAULT_END_DATE, seed=DEFAULT_RANDOM_SEED):
    """Build a deterministic salary -> spending/holding cash-flow dataset."""
    if total_count < 0:
        raise ValueError("Số giao dịch synthetic không được âm")
    if end_date < start_date:
        raise ValueError("Ngày kết thúc phải từ ngày bắt đầu trở đi")
    if start_date.day != 1 or end_date.day < 7:
        raise ValueError("Khoảng seed phải bắt đầu từ ngày 01 và kết thúc không sớm hơn ngày 07")

    months = list(_month_starts(start_date, end_date))
    recurring_count = len(months) * 6
    if total_count < recurring_count:
        raise ValueError(f"Cần ít nhất {recurring_count} giao dịch để bảo toàn dòng tiền theo tháng")
    expense_count, remainder = divmod(total_count - recurring_count, len(months))
    population = list(SPENDING_PROFILES)
    weights = [profile[1] for profile in population]
    result = {"BIDV": [], "MB": [], "VPB": []}
    for month_index, month in enumerate(months):
        rng = random.Random(_stable_seed(seed, month.strftime("%Y-%m")))
        salary = rng.randrange(250, 301) * 100_000
        bidv_transfer = rng.randrange(140, 181) * 100_000
        vpbank_transfer = salary - bidv_transfer - 2_000_000
        recurring = _recurring_rows(month, salary, bidv_transfer, vpbank_transfer)
        for bank_code, rows in recurring.items():
            result[bank_code].extend(rows)

        count = expense_count + (month_index < remainder)
        spending_target = bidv_transfer - 3_000_000 - rng.randrange(5, 16) * 100_000
        amounts = _monthly_amounts(spending_target, count, rng)
        first_day = start_date.day if month.year == start_date.year and month.month == start_date.month else 1
        last_day = end_date.day if month.year == end_date.year and month.month == end_date.month else monthrange(month.year, month.month)[1]
        spending_first_day = max(first_day, 7)
        for index, amount in enumerate(amounts, start=1):
            category, _, descriptions = rng.choices(population, weights=weights, k=1)[0]
            day = rng.randint(spending_first_day, last_day)
            posted_at = datetime(month.year, month.month, day, rng.randint(7, 22), rng.randint(0, 59), rng.randint(0, 59))
            base = rng.choice(descriptions)
            description = _synthetic_description("BIDV", base, "OUT", rng)
            ref_no = _synthetic_ref("BIDV", posted_at, seed, month_index * 10_000 + index, rng)
            result["BIDV"].append(StatementRow(posted_at, -amount, description, ref_no, category))

    for rows in result.values():
        rows.sort(key=lambda row: (row.posted_at, row.ref_no))
    return result


def _category_name(description, signed_amount):
    text = description.lower()
    if signed_amount > 0 and any(word in text for word in ("luong", "lương", "sinh hoat", "chuyển tiền đến")):
        return "Thu nhập"
    rules = (
        ("Nhà ở", ("nha tro", "nhà trọ", "tien nha")),
        ("Điện nước", ("evn", "hawacom", "tien dien", "tien nuoc")),
        ("Ăn uống", ("an uong", "com van phong", "pho 24", "highlands", "bun cha", "lotteria")),
        ("Mua sắm", ("lazada", "shopee", "uniqlo", "decathlon", "circle k", "winmart", "co.op")),
        ("Di chuyển", ("grab", "xanh sm", "metro", "thanh toan be", "xang")),
        ("Y tế", ("thuoc", "long chau", "benh vien")),
        ("Học tập", ("hoc tap", "photo", "fahasa", "nhat tao")),
        ("Viễn thông", ("internet", "viettel", "dien thoai")),
    )
    for category, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return category
    if "chuyen tien" in text or "chuyển tiền" in text:
        return "Chuyển khoản"
    return "Thu nhập" if signed_amount > 0 else "Khác"


def _get_or_create(model, defaults=None, **filters):
    item = db.session.scalar(select(model).filter_by(**filters))
    if item:
        return item, False
    item = model(**filters, **(defaults or {}))
    db.session.add(item)
    db.session.flush()
    return item, True


def _clear_demo_data(user):
    """Delete only financial data owned by one demo user, preserving identity."""
    if user.role != "USER" or not user.ledger:
        raise ValueError("Chỉ được thay dữ liệu của demo user có đúng một sổ thu chi")
    account_ids = list(db.session.scalars(select(Account.id).where(
        Account.ledger_id == user.ledger.id, Account.bank_code.in_(ACCOUNT_SPECS),
    )))
    batches = list(db.session.scalars(select(ImportBatch).where(ImportBatch.account_id.in_(account_ids)))) if account_ids else []
    foreign_batch = account_ids and db.session.scalar(select(ImportBatch.id).where(
        ImportBatch.account_id.in_(account_ids), ImportBatch.user_id != user.id,
    ).limit(1))
    if foreign_batch:
        raise ValueError("Tài khoản demo đang được import batch của user khác tham chiếu; đã hủy thay dữ liệu")

    batch_ids = [batch.id for batch in batches]
    deleted = {"imports": len(batch_ids), "accounts": len(account_ids)}
    if batch_ids:
        db.session.execute(delete(ImportError).where(ImportError.batch_id.in_(batch_ids)))
        db.session.execute(delete(ImportBatch).where(ImportBatch.id.in_(batch_ids)))
    db.session.execute(delete(Alert).where(Alert.user_id == user.id))
    db.session.execute(delete(Budget).where(Budget.user_id == user.id))
    if account_ids:
        deleted["transactions"] = db.session.execute(delete(Transaction).where(Transaction.account_id.in_(account_ids))).rowcount
        db.session.execute(delete(Account).where(Account.id.in_(account_ids)))
    else:
        deleted["transactions"] = 0
    db.session.flush()
    return deleted


def _month_starts(start_date, end_date):
    cursor = start_date.replace(day=1)
    final = end_date.replace(day=1)
    while cursor <= final:
        yield cursor
        cursor = date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)


def seed_mock(
    source_dir,
    email,
    password,
    synthetic_count=DEFAULT_SYNTHETIC_COUNT,
    random_seed=DEFAULT_RANDOM_SEED,
    start_date=DEFAULT_START_DATE,
    end_date=DEFAULT_END_DATE,
    include_source=False,
    replace_demo_data=False,
):
    files = {
        "BIDV": (source_dir / "BIDV_gia_lap_7_thang_2026.csv", parse_bidv, "4789"),
        "MB": (source_dir / "MB_gia_lap_7_thang_2026.csv", parse_mb, "2001"),
        "VPB": (source_dir / "VPBank_data_gia_thang_09_2025.csv", parse_vpbank, "7537"),
    }
    if include_source:
        missing = [str(path) for path, _, _ in files.values() if not path.is_file()]
        if missing:
            raise FileNotFoundError("Không tìm thấy file sao kê: " + ", ".join(missing))

    user, created_user = _get_or_create(
        User,
        defaults={
            "password_hash": generate_password_hash(password, method="pbkdf2:sha256:600000"),
            "full_name": "Người dùng Demo", "date_of_birth": date(1995, 5, 20),
            "consent": True, "role": "USER",
        },
        email=email.lower(),
    )
    if not user.ledger:
        user.ledger = Ledger()
        db.session.flush()
    if replace_demo_data:
        user = db.session.scalar(select(User).where(User.id == user.id).with_for_update())
        _clear_demo_data(user)

    categories = {}
    for name, nature in CATEGORY_DEFINITIONS:
        categories[name], _ = _get_or_create(Category, name=name, owner_id=None, defaults={"nature": nature})

    accounts = {}
    parsed = {bank_code: parser(path) if include_source else [] for bank_code, (path, parser, _) in files.items()}
    for bank_code, (_, _, _) in files.items():
        spec = ACCOUNT_SPECS[bank_code]
        account = db.session.scalar(select(Account).where(Account.ledger_id == user.ledger.id, Account.bank_code == bank_code))
        if not account:
            account = Account(
                ledger_id=user.ledger.id, name=spec["name"], type="BANK",
                opening_balance=spec["opening_balance"], bank_code=bank_code,
                last_four=spec["last_four"], archived=False,
            )
            db.session.add(account)
            db.session.flush()
        account.name = spec["name"]
        account.last_four = spec["last_four"]
        account.opening_balance = spec["opening_balance"]
        account.archived = False
        accounts[bank_code] = account

    synthetic = generate_synthetic_rows(synthetic_count, start_date, end_date, random_seed)
    for bank_code, rows in synthetic.items():
        parsed[bank_code].extend(rows)

    inserted = skipped = 0
    per_bank = {}
    for bank_code, rows in parsed.items():
        account = accounts[bank_code]
        bank_inserted = 0
        existing_keys = set(db.session.scalars(select(Transaction.dedup_key).where(
            Transaction.account_id == account.id,
            Transaction.dedup_key.is_not(None),
        )))
        for row in rows:
            amount = abs(row.signed_amount)
            key = dedup_key(account.id, row.posted_at, amount, row.ref_no, row.description)
            if key in existing_keys:
                skipped += 1
                continue
            category = categories[row.category_name or _category_name(row.description, row.signed_amount)]
            db.session.add(Transaction(
                account_id=account.id, category_id=category.id, posted_at=row.posted_at,
                amount=amount, direction="IN" if row.signed_amount > 0 else "OUT",
                description=row.description[:500], source="IMPORT", ref_no=row.ref_no[:100], dedup_key=key,
            ))
            inserted += 1
            bank_inserted += 1
            existing_keys.add(key)
        per_bank[bank_code] = {
            "source_rows": len(rows) - len(synthetic[bank_code]),
            "synthetic_rows": len(synthetic[bank_code]),
            "inserted": bank_inserted,
        }

    budget_plan = (
        ("Nhà ở", 3_000_000), ("Điện nước", 1_800_000), ("Ăn uống", 6_000_000),
        ("Mua sắm", 4_000_000), ("Di chuyển", 2_000_000), ("Y tế", 2_000_000),
        ("Học tập", 2_500_000), ("Viễn thông", 800_000),
    )
    for month in _month_starts(start_date, end_date):
        for category_name, amount in budget_plan:
            budget, _ = _get_or_create(Budget, user_id=user.id, category_id=categories[category_name].id, month=month, defaults={"amount": amount})
            budget.amount = amount

    db.session.commit()
    from app.services.alerts import recompute
    alerts_created = recompute(user.id, end_date)
    return {
        "email": user.email, "created_user": created_user, "inserted": inserted,
        "skipped": skipped, "accounts": len(accounts), "per_bank": per_bank,
        "synthetic_count": synthetic_count, "alerts_created": alerts_created,
        "replaced": replace_demo_data, "included_source": include_source,
    }


def main():
    parser = argparse.ArgumentParser(description="Tạo dữ liệu mock SmartExpense từ sao kê ngân hàng")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--email", default=os.getenv("MOCK_USER_EMAIL", MOCK_EMAIL))
    parser.add_argument("--password", default=os.getenv("MOCK_USER_PASSWORD", MOCK_PASSWORD))
    parser.add_argument("--synthetic-count", type=int, default=DEFAULT_SYNTHETIC_COUNT, help="Tổng giao dịch sinh thêm cho cả ba ngân hàng")
    parser.add_argument("--random-seed", type=int, default=DEFAULT_RANDOM_SEED, help="Seed để tái tạo cùng một bộ dữ liệu")
    parser.add_argument("--start-date", type=date.fromisoformat, default=DEFAULT_START_DATE, metavar="YYYY-MM-DD")
    parser.add_argument("--end-date", type=date.fromisoformat, default=DEFAULT_END_DATE, metavar="YYYY-MM-DD")
    parser.add_argument("--include-source", action="store_true", help="Nhập thêm 3 CSV gốc (không dùng cho bộ demo dòng tiền chuẩn)")
    parser.add_argument("--replace-demo-data", action="store_true", help="Xóa và tạo lại dữ liệu tài chính của đúng demo user")
    args = parser.parse_args()
    application = create_app()
    with application.app_context():
        result = seed_mock(
            args.source_dir, args.email, args.password,
            synthetic_count=args.synthetic_count,
            random_seed=args.random_seed,
            start_date=args.start_date,
            end_date=args.end_date,
            include_source=args.include_source,
            replace_demo_data=args.replace_demo_data,
        )
    print(f"Seeded {result['inserted']} transactions; skipped {result['skipped']} existing rows.")
    for bank, counts in result["per_bank"].items():
        total = counts["source_rows"] + counts["synthetic_rows"]
        print(f"  {bank}: {counts['inserted']}/{total} new ({counts['synthetic_rows']} synthetic candidates)")
    print(f"Alerts created: {result['alerts_created']}")
    print(f"Demo account: {result['email']}")
    if result["created_user"]:
        print("Demo password comes from MOCK_USER_PASSWORD (or the local-only default).")


if __name__ == "__main__":
    main()
