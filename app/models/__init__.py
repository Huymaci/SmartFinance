from datetime import date, datetime, timezone

from flask_login import UserMixin
from sqlalchemy import BigInteger, CheckConstraint, Date, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import BINARY, DATETIME
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

UTC_DATETIME = DATETIME(fsp=6)


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    consent: Mapped[bool] = mapped_column(default=False, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="USER", nullable=False)
    failed_logins: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(UTC_DATETIME)
    created_at: Mapped[datetime] = mapped_column(UTC_DATETIME, default=utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTC_DATETIME)
    deletion_requested_at: Mapped[datetime | None] = mapped_column(UTC_DATETIME)
    ledger: Mapped["Ledger"] = relationship(back_populates="user", cascade="all, delete-orphan", uselist=False)
    __table_args__ = (CheckConstraint("role IN ('USER','ADMIN')", name="ck_users_role"),)


class Ledger(db.Model):
    __tablename__ = "ledgers"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    user: Mapped[User] = relationship(back_populates="ledger")
    accounts: Mapped[list["Account"]] = relationship(back_populates="ledger", cascade="all, delete-orphan")


class Account(db.Model):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    ledger_id: Mapped[int] = mapped_column(ForeignKey("ledgers.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    opening_balance: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bank_code: Mapped[str | None] = mapped_column(String(20))
    last_four: Mapped[str | None] = mapped_column(String(4))
    archived: Mapped[bool] = mapped_column(default=False, nullable=False)
    ledger: Mapped[Ledger] = relationship(back_populates="accounts")
    __table_args__ = (CheckConstraint("type IN ('CASH','BANK')", name="ck_accounts_type"),)


class Category(db.Model):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    nature: Mapped[str | None] = mapped_column(String(20))
    __table_args__ = (
        CheckConstraint("nature IS NULL OR nature IN ('COMMITTED','SEMI_FIXED','DISCRETIONARY')", name="ck_categories_nature"),
        UniqueConstraint("owner_id", "name", name="uq_categories_owner_name"),
    )


class Transaction(db.Model):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False)
    posted_at: Mapped[datetime] = mapped_column(UTC_DATETIME, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="MANUAL", nullable=False)
    ref_no: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    dedup_key: Mapped[bytes | None] = mapped_column(BINARY(32), unique=True)
    account: Mapped[Account] = relationship()
    category: Mapped[Category] = relationship()
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transactions_amount"),
        CheckConstraint("direction IN ('IN','OUT')", name="ck_transactions_direction"),
        Index("ix_transactions_account_posted", "account_id", "posted_at"),
    )


class ImportTemplate(db.Model):
    __tablename__ = "import_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    bank_code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    mapping_json: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)


class ImportBatch(db.Model):
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    template_id: Mapped[int] = mapped_column(ForeignKey("import_templates.id", ondelete="RESTRICT"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PREVIEW", nullable=False)
    preview_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC_DATETIME, default=utcnow, nullable=False)


class ImportError(db.Model):
    __tablename__ = "import_errors"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False)
    row_number: Mapped[int] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)


class CategorizationRule(db.Model):
    __tablename__ = "categorization_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False)
    priority: Mapped[int] = mapped_column(nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    __table_args__ = (UniqueConstraint("priority", name="uq_rules_priority"),)


class Budget(db.Model):
    __tablename__ = "budgets"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_budgets_amount"),
        UniqueConstraint("user_id", "category_id", "month", name="uq_budget_user_category_month"),
    )


class Alert(db.Model):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    explanation: Mapped[str] = mapped_column(String(500), nullable=False)
    suggested_action: Mapped[str] = mapped_column(String(500), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="UNREAD", nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(UTC_DATETIME, default=utcnow, nullable=False)
    __table_args__ = (
        CheckConstraint("severity IN ('WARNING','CRITICAL')", name="ck_alerts_severity"),
        CheckConstraint("status IN ('UNREAD','READ','DISMISSED')", name="ck_alerts_status"),
        Index("ix_alerts_user_triggered", "user_id", "triggered_at"),
    )


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTC_DATETIME, default=utcnow, nullable=False)


__all__ = ["User", "Ledger", "Account", "Category", "Transaction", "ImportTemplate", "ImportBatch", "ImportError", "CategorizationRule", "Budget", "Alert", "AuditLog"]

for _table in db.metadata.tables.values():
    _table.dialect_options["mysql"]["engine"] = "InnoDB"
    _table.dialect_options["mysql"]["charset"] = "utf8mb4"
    _table.dialect_options["mysql"]["collate"] = "utf8mb4_0900_ai_ci"
