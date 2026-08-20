"""Initial schema for UC-01 through UC-05."""
from alembic import op

from app.extensions import db
from app.models import *  # noqa: F403

revision = "20260819_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    names = {"import_templates", "users", "audit_logs", "categories", "ledgers", "accounts", "import_batches", "transactions", "import_errors"}
    for table in db.metadata.sorted_tables:
        if table.name in names:
            table.create(bind, checkfirst=False)


def downgrade():
    bind = op.get_bind()
    names = {"import_templates", "users", "audit_logs", "categories", "ledgers", "accounts", "import_batches", "transactions", "import_errors"}
    for table in reversed(db.metadata.sorted_tables):
        if table.name in names:
            table.drop(bind, checkfirst=False)
