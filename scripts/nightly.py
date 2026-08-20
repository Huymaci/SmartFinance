from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import AuditLog, User
from app.services.alerts import recompute


def run():
    for user_id in db.session.scalars(select(User.id).where(User.role == "USER")):
        recompute(user_id)
    db.session.add(AuditLog(action="NIGHTLY_JOB:SUCCESS"))
    db.session.commit()


if __name__ == "__main__":
    application = create_app()
    with application.app_context():
        run()
