import io
import json
import unittest
from datetime import date

from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import Budget, CategorizationRule, Category, ImportTemplate, Transaction, User
from app.services.alerts import recompute
from config import TestConfig

PASSWORD = "StrongPass1!"


class SecondFiveUseCasesTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        db.session.add_all([
            Category(id=1, name="Ăn uống", nature="DISCRETIONARY"),
            Category(id=2, name="Nhà ở", nature="COMMITTED"),
            Category(id=3, name="Điện nước", nature="SEMI_FIXED"),
            ImportTemplate(id=1, bank_code="VCB", name="VCB CSV", active=True, mapping_json=json.dumps({"header_rows": 1, "date": 0, "description": 1, "amount": 2, "ref_no": 3, "date_format": "%Y-%m-%d"})),
        ])
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def register_login(self, email="user@example.com"):
        response = self.client.post("/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Nguyễn An", "date_of_birth": "1995-04-10", "consent": False})
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(self.client.post("/auth/login", json={"email": email, "password": PASSWORD}).status_code, 200)
        return db.session.query(User).filter_by(email=email).one()

    def cash_account(self, balance=1_000_000):
        response = self.client.post("/accounts", json={"name": "Ví", "type": "CASH", "opening_balance": balance})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["id"]

    def transaction(self, account_id, amount, category=1, posted="2026-08-15", direction="OUT"):
        response = self.client.post("/transactions", json={"date": posted, "amount": amount, "direction": direction, "account_id": account_id, "category_id": category, "description": "Test"})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["id"]

    def test_uc06_conflict_decision_atomic_confirm_error_report_and_idempotence(self):
        self.register_login()
        account_id = self.cash_account()
        self.transaction(account_id, 50_000, posted="2026-08-01")
        content = b"date,description,amount,ref\n2026-08-02,Coffee,-50000,A1\nbad,Broken,-1,A2\n"
        preview = self.client.post("/imports/preview", data={"account_id": str(account_id), "template_id": "1", "file": (io.BytesIO(content), "statement.csv")}, content_type="multipart/form-data")
        self.assertEqual(preview.status_code, 201, preview.get_json())
        summary = preview.get_json()
        self.assertEqual(summary["probable_duplicate"], 1)
        self.assertEqual(self.client.post(f"/imports/{summary['batch_id']}/confirm", json={}).status_code, 400)
        confirmed = self.client.post(f"/imports/{summary['batch_id']}/confirm", json={"decisions": {"2": "KEEP"}, "category_overrides": {"2": 1}})
        self.assertEqual(confirmed.status_code, 201, confirmed.get_json())
        self.assertEqual(confirmed.get_json()["imported"], 1)
        self.assertEqual(db.session.query(Transaction).filter_by(source="IMPORT").count(), 1)
        report = self.client.get(f"/imports/{summary['batch_id']}/errors.csv")
        self.assertIn(b"row_number,reason", report.data)
        repeated = self.client.post("/imports/preview", data={"account_id": str(account_id), "template_id": "1", "file": (io.BytesIO(content), "statement.csv")}, content_type="multipart/form-data").get_json()
        self.assertEqual(repeated["new"], 0)
        self.assertEqual(repeated["duplicate"], 1)

    def test_uc06_ordered_classification_merge_and_access_control(self):
        self.register_login()
        account_id = self.cash_account()
        db.session.add(CategorizationRule(pattern=r"ca phe|coffee", category_id=1, priority=10, active=True))
        db.session.commit()
        content = b"date,description,amount,ref\n2026-08-03,Ca phe,-50000,A3\n"
        preview = self.client.post("/imports/preview", data={"account_id": str(account_id), "template_id": "1", "file": (io.BytesIO(content), "classify.csv")}, content_type="multipart/form-data").get_json()
        confirmed = self.client.post(f"/imports/{preview['batch_id']}/confirm", json={})
        self.assertEqual(confirmed.status_code, 201, confirmed.get_json())
        imported = db.session.query(Transaction).filter_by(source="IMPORT").one()
        self.assertEqual(imported.category_id, 1)
        self.assertEqual(self.client.post(f"/imports/{preview['batch_id']}/confirm", json={}).status_code, 400)
        self.client.post("/auth/logout")
        self.register_login("other@example.com")
        self.assertEqual(self.client.get(f"/imports/{preview['batch_id']}/errors.csv").status_code, 404)

    def test_uc07_monthly_budget_copy_and_safe_to_spend(self):
        self.register_login()
        account_id = self.cash_account()
        self.transaction(account_id, 100_000, category=2)
        budget = self.client.put("/budgets", json={"month": "2026-08", "category_id": 2, "amount": 400_000})
        self.assertEqual(budget.status_code, 200, budget.get_json())
        safe = self.client.get("/budgets/safe-to-spend?month=2026-08").get_json()["amount"]
        self.assertEqual(safe, 600_000)
        copied = self.client.post("/budgets/copy", json={"month": "2026-09"}).get_json()
        self.assertEqual(copied["copied"], 1)
        self.assertEqual(self.client.get("/budgets?month=2026-09").get_json()["items"][0]["amount"], 400_000)

    def test_uc08_threshold_burn_rate_cooldown_and_inbox_actions(self):
        user = self.register_login()
        account_id = self.cash_account()
        self.transaction(account_id, 85_000, posted="2026-08-15")
        db.session.add(Budget(user_id=user.id, category_id=1, month=date(2026, 8, 1), amount=100_000))
        db.session.commit()
        self.assertEqual(recompute(user.id, date(2026, 8, 15)), 2)
        self.assertEqual(recompute(user.id, date(2026, 8, 15)), 0)
        self.transaction(account_id, 20_000, posted="2026-08-15")
        self.assertEqual(recompute(user.id, date(2026, 8, 15)), 1)
        inbox = self.client.get("/alerts").get_json()["items"]
        self.assertEqual({item["kind"] for item in inbox}, {"THRESHOLD", "BURN_RATE"})
        self.assertTrue(all(item["explanation"] and item["suggested_action"] for item in inbox))
        changed = self.client.patch(f"/alerts/{inbox[0]['id']}", json={"status": "DISMISSED"})
        self.assertEqual(changed.get_json()["status"], "DISMISSED")

    def test_uc09_dashboard_breakdown_and_twelve_month_trend(self):
        self.register_login()
        account_id = self.cash_account()
        self.transaction(account_id, 200_000, direction="IN")
        self.transaction(account_id, 85_000)
        user = db.session.query(User).filter_by(email="user@example.com").one()
        db.session.add(Budget(user_id=user.id, category_id=1, month=date(2026, 8, 1), amount=100_000))
        db.session.commit()
        dashboard = self.client.get("/statistics/dashboard?month=2026-08").get_json()
        self.assertEqual((dashboard["income"], dashboard["expense"], dashboard["net"]), (200_000, 85_000, 115_000))
        self.assertEqual((dashboard["budget_progress"][0]["status"], dashboard["budget_progress"][0]["label"]), ("AMBER", "Sắp chạm ngân sách"))
        breakdown_response = self.client.get("/statistics/breakdown?date_from=2026-08-01&date_to=2026-08-31").get_json()
        breakdown = breakdown_response["items"]
        self.assertEqual(breakdown[0]["amount"], 85_000)
        self.assertEqual(breakdown_response["total_expense"], sum(item["amount"] for item in breakdown_response["items"]))
        self.assertEqual(len(self.client.get("/statistics/trend?through=2026-08").get_json()["items"]), 12)

    def test_uc11_admin_metadata_only_lock_reset_config_suppression_and_delete(self):
        user = self.register_login()
        account_id = self.cash_account()
        self.transaction(account_id, 123_456, posted="2026-08-01")
        self.assertEqual(self.client.get("/admin/users").status_code, 403)
        self.assertEqual(self.client.post("/profile/deletion-request").status_code, 202)
        self.client.post("/auth/logout")
        admin = User(email="admin@example.com", full_name="Admin", date_of_birth=date(1990, 1, 1), consent=False, role="ADMIN", password_hash=generate_password_hash(PASSWORD, method="pbkdf2:sha256:600000"))
        db.session.add(admin)
        db.session.commit()
        self.assertEqual(self.client.post("/auth/login", json={"email": admin.email, "password": PASSWORD}).status_code, 200)
        listing = self.client.get("/admin/users").get_json()["items"][0]
        self.assertFalse({"balance", "transactions", "amount", "description"} & set(listing))
        self.assertEqual(self.client.post(f"/admin/users/{user.id}/lock").status_code, 200)
        self.assertEqual(self.client.post(f"/admin/users/{user.id}/unlock").status_code, 200)
        reset = self.client.post(f"/admin/users/{user.id}/reset-password")
        self.assertTrue(reset.get_json()["temporary_password"])
        self.assertTrue(self.client.get("/admin/operations").get_json()["suppressed"])
        self.assertEqual(self.client.patch("/admin/import-config/template/1", json={"active": False}).get_json()["active"], False)
        self.assertEqual(self.client.delete(f"/admin/users/{user.id}").status_code, 200)
        self.assertIsNone(db.session.get(User, user.id))
        self.assertEqual(db.session.query(Transaction).count(), 0)


if __name__ == "__main__":
    unittest.main()
