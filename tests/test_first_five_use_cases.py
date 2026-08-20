import io
import json
import unittest
import zipfile

from werkzeug.security import check_password_hash

from app import create_app
from app.extensions import db
from app.models import Account, Category, ImportBatch, ImportTemplate, Transaction, User
from app.services.common import ValidationError
from app.services.imports import _parse_row, _table, _xlsx_rows
from config import TestConfig

PASSWORD = "StrongPass1!"


class FirstFiveUseCasesTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        db.session.add(Category(id=1, name="Ăn uống", nature="DISCRETIONARY"))
        db.session.add(ImportTemplate(id=1, bank_code="VCB", name="VCB CSV", active=True, mapping_json=json.dumps({"header_rows": 1, "date": 0, "description": 1, "amount": 2, "ref_no": 3, "date_format": "%Y-%m-%d"})))
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def register(self, email="user@example.com"):
        return self.client.post("/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Nguyễn An", "date_of_birth": "1995-04-10", "consent": False})

    def login(self, email="user@example.com", password=PASSWORD):
        return self.client.post("/auth/login", json={"email": email, "password": password})

    def register_and_login(self, email="user@example.com"):
        self.assertEqual(self.register(email).status_code, 201)
        self.assertEqual(self.login(email).status_code, 200)

    def create_cash_account(self, name="Ví"):
        response = self.client.post("/accounts", json={"name": name, "type": "CASH", "opening_balance": 1_000_000})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["id"]

    def test_uc01_register_creates_ledger_hashes_password_and_login_lockout(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        user = db.session.query(User).filter_by(email="user@example.com").one()
        self.assertIsNotNone(user.ledger)
        self.assertNotEqual(user.password_hash, PASSWORD)
        self.assertTrue(check_password_hash(user.password_hash, PASSWORD))
        self.assertFalse(user.consent)
        self.assertFalse(self.client.get("/auth/privacy-notice").get_json()["consent_default"])
        for _ in range(5):
            failure = self.login(password="wrong-password")
        self.assertEqual(failure.status_code, 400)
        self.assertIsNotNone(db.session.get(User, user.id).locked_until)
        self.assertIn("tạm khóa", self.login().get_json()["error"])

    def test_uc02_profile_password_export_logout_and_deletion_request(self):
        self.register_and_login()
        self.assertEqual(self.client.patch("/profile", json={"full_name": "Nguyễn Bình", "consent": True}).status_code, 200)
        self.assertEqual(self.client.post("/profile/change-password", json={"current_password": PASSWORD, "new_password": "NewStrong2@"}).status_code, 200)
        export = self.client.get("/profile/export")
        self.assertEqual(export.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(export.data)) as archive:
            self.assertEqual(set(archive.namelist()), {"smartfinance.json", "transactions.csv"})
            exported = json.loads(archive.read("smartfinance.json"))
            self.assertEqual(exported["profile"]["full_name"], "Nguyễn Bình")
            self.assertTrue(
                {"accounts", "transactions", "custom_categories", "budgets", "alerts", "imports", "import_errors", "audit_logs"}
                <= set(exported)
            )
        self.assertEqual(self.client.post("/profile/deletion-request").status_code, 202)
        self.assertIsNotNone(db.session.query(User).one().deletion_requested_at)
        self.assertEqual(self.client.post("/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/profile").status_code, 401)

    def test_uc03_account_crud_archives_and_rejects_sensitive_bank_fields(self):
        self.register_and_login()
        account_id = self.create_cash_account()
        update = self.client.put(f"/accounts/{account_id}", json={"name": "VCB", "type": "BANK", "opening_balance": 2_000_000, "bank_code": "VCB", "last_four": "1234"})
        self.assertEqual(update.status_code, 200)
        rejected = self.client.post("/accounts", json={"name": "Sai", "type": "BANK", "opening_balance": 0, "last_four": "1234", "account_number": "123456789"})
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(self.client.delete(f"/accounts/{account_id}").status_code, 200)
        self.assertTrue(db.session.get(Account, account_id).archived)
        listed = next(item for item in self.client.get("/accounts").get_json()["items"] if item["id"] == account_id)
        self.assertTrue(listed["archived"])
        self.client.post("/auth/logout")
        self.register_and_login("other@example.com")
        self.assertEqual(self.client.post(f"/accounts/{account_id}/restore").status_code, 404)
        self.assertTrue(db.session.get(Account, account_id).archived)
        self.client.post("/auth/logout")
        self.assertEqual(self.login().status_code, 200)
        restored = self.client.post(f"/accounts/{account_id}/restore")
        self.assertEqual(restored.status_code, 200)
        self.assertFalse(restored.get_json()["archived"])
        self.assertFalse(db.session.get(Account, account_id).archived)

    def test_uc04_transaction_crud_filters_paginates_and_hides_other_users(self):
        self.register_and_login()
        account_id = self.create_cash_account()
        payload = {"date": "2026-08-19", "amount": 120000, "direction": "OUT", "account_id": account_id, "category_id": 1, "description": "Bữa tối"}
        created = self.client.post("/transactions", json=payload)
        self.assertEqual(created.status_code, 201, created.get_json())
        transaction_id = created.get_json()["id"]
        self.assertEqual(self.client.get(f"/transactions/{transaction_id}").status_code, 200)
        listing = self.client.get(f"/transactions?direction=OUT&account_id={account_id}&date_from=2026-08-01&page=1&per_page=1").get_json()
        self.assertEqual(listing["total"], 1)
        payload["amount"] = 130000
        self.assertEqual(self.client.put(f"/transactions/{transaction_id}", json=payload).status_code, 200)
        self.client.post("/auth/logout")
        self.register_and_login("other@example.com")
        self.assertEqual(self.client.get(f"/transactions/{transaction_id}").status_code, 404)
        self.assertEqual(self.client.put(f"/transactions/{transaction_id}", json=payload).status_code, 404)
        self.assertEqual(self.client.delete(f"/transactions/{transaction_id}").status_code, 404)

    def test_uc04_custom_category_rename_delete_requires_reassignment(self):
        self.register_and_login()
        account_id = self.create_cash_account()
        created = self.client.post("/categories", json={"name": "Thú cưng", "nature": "DISCRETIONARY", "parent_id": 1})
        self.assertEqual(created.status_code, 201, created.get_json())
        category_id = created.get_json()["id"]
        self.assertEqual(self.client.patch(f"/categories/{category_id}", json={"name": "Chăm sóc thú cưng"}).status_code, 200)
        transaction = self.client.post("/transactions", json={"date": "2026-08-19", "amount": 100000, "direction": "OUT", "account_id": account_id, "category_id": category_id, "description": "Thức ăn"}).get_json()
        rejected = self.client.delete(f"/categories/{category_id}", json={"reassign_to": category_id})
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(self.client.delete(f"/categories/{category_id}", json={"reassign_to": 1}).status_code, 200)
        self.assertEqual(db.session.get(Transaction, transaction["id"]).category_id, 1)

    def test_uc05_csv_preview_counts_new_duplicates_errors_without_writing(self):
        self.register_and_login()
        account_id = self.create_cash_account()
        content = b"date,description,amount,ref\n2026-08-01,Coffee,-50000,A1\n2026-08-01,Coffee,-50000,A1\nbad-date,Broken,-10,A2\n"
        response = self.client.post("/imports/preview", data={"account_id": str(account_id), "template_id": "1", "file": (io.BytesIO(content), "statement.csv")}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(response.get_json()["new"], 1)
        self.assertEqual(response.get_json()["duplicate"], 1)
        self.assertEqual(response.get_json()["error"], 1)
        self.assertEqual(db.session.query(Transaction).count(), 0)
        self.assertEqual(db.session.query(ImportBatch).one().status, "PREVIEW")

    def test_uc05_rejects_renamed_executable(self):
        self.register_and_login()
        account_id = self.create_cash_account()
        response = self.client.post("/imports/preview", data={"account_id": str(account_id), "template_id": "1", "file": (io.BytesIO(b"MZ\x00\x00evil"), "statement.xlsx")}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)
        self.assertIn("magic byte", response.get_json()["error"])

    def test_uc05_xlsx_cells_and_separate_debit_credit_columns(self):
        workbook = io.BytesIO()
        shared = b'''<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>date</t></si><si><t>description</t></si><si><t>2026-08-01</t></si><si><t>Ca phe</t></si></sst>'''
        sheet = b'''<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1" t="s"><v>1</v></c></row><row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" t="s"><v>3</v></c><c r="C2"><v>50000</v></c></row></sheetData></worksheet>'''
        with zipfile.ZipFile(workbook, "w") as archive:
            archive.writestr("xl/sharedStrings.xml", shared)
            archive.writestr("xl/worksheets/sheet1.xml", sheet)
        rows = _xlsx_rows(workbook.getvalue())
        self.assertEqual(rows[0], ["date", "", "description"])
        self.assertEqual(rows[1], ["2026-08-01", "Ca phe", "50000"])
        parsed = _parse_row(["2026-08-01", "Merchant", "50000", "", "REF"], {"date": 0, "description": 1, "debit": 2, "credit": 3, "ref_no": 4, "date_format": "%Y-%m-%d"})
        self.assertEqual((parsed[1], parsed[2]), (50000, "OUT"))

    def test_uc05_parser_validation_branches(self):
        credit = _parse_row(["2026-08-01", "Merchant", "", "75,000"], {"date": 0, "description": 1, "debit": 2, "credit": 3})
        self.assertEqual((credit[1], credit[2]), (75000, "IN"))
        with self.assertRaises(ValueError):
            _parse_row(["2026-08-01", "Merchant", "", ""], {"date": 0, "description": 1, "debit": 2, "credit": 3})
        with self.assertRaises(ValueError):
            _parse_row(["2026-08-01", "Merchant", "0"], {"date": 0, "description": 1, "amount": 2})
        with self.assertRaises(ValidationError):
            _table(b"a\x00b", ".csv")
        with self.assertRaises(ValidationError):
            _table(b"\xff\xfe", ".csv")
        empty_xlsx = io.BytesIO()
        with zipfile.ZipFile(empty_xlsx, "w") as archive:
            archive.writestr("docProps/app.xml", "<root/>")
        with self.assertRaises(ValidationError):
            _xlsx_rows(empty_xlsx.getvalue())


if __name__ == "__main__":
    unittest.main()
