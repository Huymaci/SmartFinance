"""Schema for UC-06 through UC-11 Must features."""
from alembic import op

from app.extensions import db
from app.models import *  # noqa: F403

revision = "20260819_02"
down_revision = "20260819_01"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    names = {"categorization_rules", "budgets", "alerts"}
    for table in db.metadata.sorted_tables:
        if table.name in names:
            table.create(bind, checkfirst=False)


def downgrade():
    bind = op.get_bind()
    names = {"categorization_rules", "budgets", "alerts"}
    for table in reversed(db.metadata.sorted_tables):
        if table.name in names:
            table.drop(bind, checkfirst=False)
