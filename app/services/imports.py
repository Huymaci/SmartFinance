import csv
import hashlib
import io
import json
import os
import re
import unicodedata
import zipfile
from datetime import datetime, timedelta
from xml.etree import ElementTree

from sqlalchemy import select
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import CategorizationRule, Category, ImportBatch, ImportError, ImportTemplate, Transaction
from app.repositories import AccountRepository

from .common import ValidationError, owned_or_404

ALLOWED = {".csv", ".xlsx"}


def dedup_key(account_id, posted_at, amount, ref_no, description):
    canonical = "|".join((str(account_id), posted_at.date().isoformat(), str(amount), ref_no.strip(), description.strip()))
    return hashlib.sha256(canonical.encode("utf-8")).digest()


def _xlsx_rows(content):
    if not content.startswith(b"PK\x03\x04"):
        raise ValidationError("Tệp XLSX không có magic byte ZIP hợp lệ")
    with zipfile.ZipFile(io.BytesIO(content)) as package:
        shared = []
        if "xl/sharedStrings.xml" in package.namelist():
            root = ElementTree.fromstring(package.read("xl/sharedStrings.xml"))
            shared = ["".join(node.text or "" for node in item.iter() if node.tag.endswith("}t")) for item in root]
        sheet_name = next((name for name in package.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")), None)
        if not sheet_name:
            raise ValidationError("Không tìm thấy worksheet trong XLSX")
        root = ElementTree.fromstring(package.read(sheet_name))
        table = []
        for row in (n for n in root.iter() if n.tag.endswith("}row")):
            values = []
            for cell in (n for n in row if n.tag.endswith("}c")):
                reference = cell.attrib.get("r", "A1")
                letters = re.match(r"[A-Z]+", reference).group(0)
                column = 0
                for letter in letters:
                    column = column * 26 + ord(letter) - 64
                while len(values) < column - 1:
                    values.append("")
                raw = next((n.text or "" for n in cell.iter() if n.tag.endswith("}v")), "")
                if cell.attrib.get("t") == "inlineStr":
                    raw = "".join(n.text or "" for n in cell.iter() if n.tag.endswith("}t"))
                values.append(shared[int(raw)] if cell.attrib.get("t") == "s" and raw else raw)
            table.append(values)
        return table


def _table(content, extension):
    if extension == ".xlsx":
        return _xlsx_rows(content)
    if b"\x00" in content[:1024]:
        raise ValidationError("Tệp CSV không hợp lệ")
    try:
        return list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
    except UnicodeDecodeError as exc:
        raise ValidationError("CSV phải dùng UTF-8") from exc


def _parse_row(row, mapping):
    def value(key):
        column = mapping.get(key)
        if column is None or column >= len(row):
            return ""
        return str(row[column]).strip()
    posted_at = datetime.strptime(value("date"), mapping.get("date_format", "%Y-%m-%d"))
    description = value("description")
    ref_no = value("ref_no")
    if mapping.get("amount") is not None:
        signed = int(round(float(value("amount").replace(",", ""))))
        direction = "IN" if signed >= 0 else "OUT"
        amount = abs(signed)
    else:
        debit = value("debit")
        credit = value("credit")
        if debit:
            amount, direction = int(round(float(debit.replace(",", "")))), "OUT"
        elif credit:
            amount, direction = int(round(float(credit.replace(",", "")))), "IN"
        else:
            raise ValueError("Thiếu số tiền ghi nợ/ghi có")
    if amount <= 0:
        raise ValueError("Số tiền phải lớn hơn 0")
    return posted_at, amount, direction, ref_no, description


def preview(user, account_id, template_id, uploaded):
    account = owned_or_404(AccountRepository.owned(account_id, user.id, include_archived=False))
    template = db.session.scalar(select(ImportTemplate).where(ImportTemplate.id == template_id, ImportTemplate.active.is_(True)))
    if not template:
        raise ValidationError("Import template không tồn tại hoặc đã tắt")
    filename = secure_filename(uploaded.filename or "")
    extension = os.path.splitext(filename)[1].lower()
    if extension not in ALLOWED:
        raise ValidationError("Chỉ chấp nhận .csv hoặc .xlsx")
    content = uploaded.read()
    rows = _table(content, extension)
    mapping = json.loads(template.mapping_json)
    results, errors, duplicates, probable = [], [], 0, 0
    seen = set()
    existing = set(db.session.scalars(select(Transaction.dedup_key).where(Transaction.account_id == account.id, Transaction.dedup_key.is_not(None))))
    start = int(mapping.get("header_rows", 1))
    for row_number, row in enumerate(rows[start:], start=start + 1):
        try:
            posted_at, amount, direction, ref_no, description = _parse_row(row, mapping)
            key = dedup_key(account.id, posted_at, amount, ref_no, description)
            if key in existing or key in seen:
                duplicates += 1
                continue
            seen.add(key)
            fuzzy = db.session.scalar(select(Transaction.id).where(
                Transaction.account_id == account.id,
                Transaction.source == "MANUAL",
                Transaction.posted_at >= posted_at - timedelta(days=1),
                Transaction.posted_at <= posted_at + timedelta(days=1),
                Transaction.amount >= int(amount * 0.99),
                Transaction.amount <= int(amount * 1.01),
            ).limit(1))
            if fuzzy:
                probable += 1
            results.append({"row_number": row_number, "date": posted_at.date().isoformat(), "amount": amount, "direction": direction, "ref_no": ref_no, "description": description, "dedup_key": key.hex(), "probable_duplicate_id": fuzzy})
        except (ValueError, IndexError) as exc:
            errors.append({"row_number": row_number, "reason": str(exc)})
    summary = {
        "new": len(results),
        "duplicate": duplicates,
        "probable_duplicate": probable,
        "error": len(errors),
        "sample": results[:10],
        "conflicts": [row for row in results if row.get("probable_duplicate_id")],
        "errors": errors,
    }
    batch = ImportBatch(user_id=user.id, account_id=account.id, template_id=template.id, filename=filename, preview_json=json.dumps({"summary": summary, "rows": results}, ensure_ascii=False))
    db.session.add(batch)
    db.session.flush()
    db.session.add_all(ImportError(batch_id=batch.id, **error) for error in errors)
    db.session.commit()
    summary["batch_id"] = batch.id
    return summary


def _normalise(value):
    decomposed = unicodedata.normalize("NFKD", value.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _classified_category(description):
    rules = db.session.scalars(select(CategorizationRule).where(CategorizationRule.active.is_(True)).order_by(CategorizationRule.priority)).all()
    merchant = _normalise(description)
    for rule in rules:
        if re.search(rule.pattern, merchant, re.IGNORECASE):
            return rule.category_id
    category = db.session.scalar(select(Category).where(Category.name == "Uncategorised", Category.owner_id.is_(None)))
    if not category:
        category = Category(name="Uncategorised", nature="DISCRETIONARY")
        db.session.add(category)
        db.session.flush()
    return category.id


def confirm(user, batch_id, decisions=None, category_overrides=None):
    batch = db.session.scalar(select(ImportBatch).where(ImportBatch.id == batch_id, ImportBatch.user_id == user.id, ImportBatch.status == "PREVIEW"))
    if not batch:
        raise ValidationError("Batch preview không tồn tại hoặc đã được xử lý")
    decisions = decisions or {}
    category_overrides = category_overrides or {}
    payload = json.loads(batch.preview_json)
    added = 0
    try:
        for row in payload["rows"]:
            row_key = str(row["row_number"])
            if row.get("probable_duplicate_id") and decisions.get(row_key) not in {"KEEP", "MERGE"}:
                raise ValidationError(f"Cần chọn MERGE hoặc KEEP cho dòng {row_key}")
            if decisions.get(row_key) == "MERGE":
                continue
            raw_key = bytes.fromhex(row["dedup_key"])
            if db.session.scalar(select(Transaction.id).where(Transaction.dedup_key == raw_key)):
                continue
            category_id = category_overrides.get(row_key) or _classified_category(row["description"])
            category = db.session.scalar(select(Category).where(Category.id == int(category_id), (Category.owner_id.is_(None)) | (Category.owner_id == user.id)))
            if not category:
                raise ValidationError(f"Category override không hợp lệ tại dòng {row_key}")
            db.session.add(Transaction(account_id=batch.account_id, category_id=category.id, posted_at=datetime.strptime(row["date"], "%Y-%m-%d"), amount=row["amount"], direction=row["direction"], description=row["description"], ref_no=row["ref_no"], source="IMPORT", dedup_key=raw_key))
            added += 1
        batch.status = "COMMITTED"
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    from .alerts import recompute
    recompute(user.id)
    return added


def error_csv(user, batch_id):
    batch = db.session.scalar(select(ImportBatch).where(ImportBatch.id == batch_id, ImportBatch.user_id == user.id))
    if not batch:
        from flask import abort
        abort(404)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["row_number", "reason"])
    for error in db.session.scalars(select(ImportError).where(ImportError.batch_id == batch.id).order_by(ImportError.row_number)):
        writer.writerow([error.row_number, error.reason])
    return io.BytesIO(output.getvalue().encode("utf-8-sig"))
