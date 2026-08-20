"""Seed realistic SmartExpense demo data from the supplied mock bank statements.

Usage (after migrations):
    python -m scripts.seed_mock --source-dir "D:\\.Giả lập dữ liệu"

The command is idempotent: users/accounts/categories/budgets are reused and
transactions are de-duplicated with the same key as the statement importer.
"""

import argparse
import csv
import os
import random
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import Account, Budget, Category, Ledger, Transaction, User
from app.services.imports import dedup_key

DEFAULT_SOURCE_DIR = Path(r"D:\.Giả lập dữ liệu")
MOCK_EMAIL = "demo@smartexpense.local"
MOCK_PASSWORD = "SmartExpenseMock1!"
# The three source statements contain 283 rows. Adding 19,717 reaches the
# 20,000-transaction dataset required by NFR-08 in the slim SRS.
DEFAULT_SYNTHETIC_COUNT = 19_717
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


# category, direction, weight, min/max amount and descriptions. The relative
# frequencies and merchant vocabulary are based on the three supplied files.
SYNTHETIC_PROFILES = (
    ("Ăn uống", "OUT", 30, 20_000, 280_000, ("THANH TOAN AN UONG COM VAN PHONG", "PHO 24", "HIGHLANDS COFFEE", "BUN CHA HA NOI", "LOTTERIA")),
    ("Mua sắm", "OUT", 20, 35_000, 1_800_000, ("LAZADA THANH TOAN DON HANG", "SHOPEE MUA SAM", "WINMART MUA THUC PHAM", "CO.OP FOOD", "UNIQLO")),
    ("Di chuyển", "OUT", 15, 10_000, 450_000, ("THANH TOAN GRAB", "THANH TOAN BE", "DI CHUYEN XANH SM", "HANOI METRO", "DO XANG PETROLIMEX")),
    ("Điện nước", "OUT", 5, 120_000, 1_500_000, ("THANH TOAN TIEN DIEN EVNHANOI", "THANH TOAN TIEN NUOC HAWACOM")),
    ("Viễn thông", "OUT", 5, 50_000, 550_000, ("THANH TOAN CUOC INTERNET VIETTEL", "NAP TIEN DIEN THOAI", "THANH TOAN FPT TELECOM")),
    ("Y tế", "OUT", 4, 50_000, 3_500_000, ("NHA THUOC LONG CHAU", "KHAM BENH MEDLATEC", "THANH TOAN BENH VIEN")),
    ("Học tập", "OUT", 4, 25_000, 2_500_000, ("CHI PHI HOC TAP", "FAHASA MUA SACH", "PHOTO NGUYEN PHONG IN TAI LIEU")),
    ("Nhà ở", "OUT", 3, 2_500_000, 7_500_000, ("CHUYEN TIEN NHA TRO", "THANH TOAN TIEN NHA")),
    ("Thu nhập", "IN", 5, 1_000_000, 28_000_000, ("LUONG THANG CONG TY TNHH CONG NGHE VIET", "THU NHAP FREELANCE", "THUONG DU AN")),
    ("Chuyển khoản", None, 7, 100_000, 8_000_000, ("NGUYEN TUAN HUY CHUYEN TIEN", "NHAN TIEN CHUYEN KHOAN", "CHUYEN TIEN CHI TIEU")),
    ("Khác", "OUT", 2, 20_000, 2_000_000, ("THANH TOAN DICH VU", "PHI DICH VU NGAN HANG", "CHI TIEU KHAC")),
)


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


def _random_timestamp(rng, start_date, end_date):
    start = datetime.combine(start_date, datetime.min.time())
    seconds = int((datetime.combine(end_date + timedelta(days=1), datetime.min.time()) - start).total_seconds())
    return start + timedelta(seconds=rng.randrange(seconds))


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


def generate_synthetic_rows(total_count, start_date=DEFAULT_START_DATE, end_date=DEFAULT_END_DATE, seed=DEFAULT_RANDOM_SEED):
    """Return deterministic statement-like rows split across the three banks."""
    if total_count < 0:
        raise ValueError("Số giao dịch synthetic không được âm")
    if end_date < start_date:
        raise ValueError("Ngày kết thúc phải từ ngày bắt đầu trở đi")

    bidv_count = total_count * 15 // 100
    mb_count = total_count * 72 // 100
    counts = {"BIDV": bidv_count, "MB": mb_count, "VPB": total_count - bidv_count - mb_count}
    population = list(SYNTHETIC_PROFILES)
    weights = [profile[2] for profile in population]
    result = {}
    for bank_offset, (bank_code, count) in enumerate(counts.items(), start=1):
        rng = random.Random(seed + bank_offset * 1_000_003)
        rows = []
        for index in range(1, count + 1):
            category, fixed_direction, _, minimum, maximum, descriptions = rng.choices(population, weights=weights, k=1)[0]
            direction = fixed_direction or ("IN" if rng.random() < 0.35 else "OUT")
            posted_at = _random_timestamp(rng, start_date, end_date)
            amount = rng.randrange((minimum + 999) // 1_000, maximum // 1_000 + 1) * 1_000
            base = rng.choice(descriptions)
            description = _synthetic_description(bank_code, base, direction, rng)
            ref_no = _synthetic_ref(bank_code, posted_at, seed, index, rng)
            rows.append(StatementRow(
                posted_at=posted_at,
                signed_amount=amount if direction == "IN" else -amount,
                description=description,
                ref_no=ref_no,
                category_name=category,
            ))
        result[bank_code] = rows
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
):
    files = {
        "BIDV": (source_dir / "BIDV_gia_lap_7_thang_2026.csv", parse_bidv, "4789"),
        "MB": (source_dir / "MB_gia_lap_7_thang_2026.csv", parse_mb, "2001"),
        "VPB": (source_dir / "VPBank_data_gia_thang_09_2025.csv", parse_vpbank, "7537"),
    }
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

    categories = {}
    for name, nature in CATEGORY_DEFINITIONS:
        categories[name], _ = _get_or_create(Category, name=name, owner_id=None, defaults={"nature": nature})

    accounts = {}
    parsed = {}
    for bank_code, (path, parser, last_four) in files.items():
        parsed[bank_code] = parser(path)
        account = db.session.scalar(select(Account).where(Account.ledger_id == user.ledger.id, Account.bank_code == bank_code))
        if not account:
            account = Account(
                ledger_id=user.ledger.id, name=f"Tài khoản {bank_code}", type="BANK",
                opening_balance=0, bank_code=bank_code, last_four=last_four,
            )
            db.session.add(account)
            db.session.flush()
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
        ("Nhà ở", 6_000_000), ("Điện nước", 1_800_000), ("Ăn uống", 5_000_000),
        ("Mua sắm", 4_000_000), ("Di chuyển", 2_000_000), ("Y tế", 2_000_000),
        ("Học tập", 2_500_000), ("Viễn thông", 800_000),
    )
    for month in _month_starts(start_date, end_date):
        for category_name, amount in budget_plan:
            _get_or_create(Budget, user_id=user.id, category_id=categories[category_name].id, month=month, defaults={"amount": amount})

    db.session.commit()
    from app.services.alerts import recompute
    alerts_created = recompute(user.id, end_date)
    return {
        "email": user.email, "created_user": created_user, "inserted": inserted,
        "skipped": skipped, "accounts": len(accounts), "per_bank": per_bank,
        "synthetic_count": synthetic_count, "alerts_created": alerts_created,
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
    args = parser.parse_args()
    application = create_app()
    with application.app_context():
        result = seed_mock(
            args.source_dir, args.email, args.password,
            synthetic_count=args.synthetic_count,
            random_seed=args.random_seed,
            start_date=args.start_date,
            end_date=args.end_date,
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
