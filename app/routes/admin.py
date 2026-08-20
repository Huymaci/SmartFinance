from functools import wraps

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required

from app.models import CategorizationRule, ImportTemplate
from app.services import admin as service

from .helpers import json_body, validation_response

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(function):
    @wraps(function)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "ADMIN":
            abort(403)
        return function(*args, **kwargs)
    return wrapped


@admin_bp.get("/users")
@admin_required
def users():
    page = service.search_users(request.args.get("q", ""), request.args.get("page", 1, type=int), min(request.args.get("per_page", 20, type=int), 100))
    return jsonify(items=[service.metadata(item) for item in page.items], total=page.total, page=page.page, pages=page.pages)


@admin_bp.post("/users/<int:user_id>/lock")
@admin_required
def lock_user(user_id):
    service.lock(user_id, True)
    return jsonify(message="Đã khóa")


@admin_bp.post("/users/<int:user_id>/unlock")
@admin_required
def unlock_user(user_id):
    service.lock(user_id, False)
    return jsonify(message="Đã mở khóa")


@admin_bp.post("/users/<int:user_id>/reset-password")
@admin_required
def reset_password(user_id):
    return jsonify(temporary_password=service.reset_password(user_id))


@admin_bp.delete("/users/<int:user_id>")
@admin_required
def delete_user(user_id):
    return validation_response(lambda: (service.execute_deletion(user_id), jsonify(message="Đã xóa dữ liệu cá nhân"))[1])


@admin_bp.get("/import-config")
@admin_required
def import_config():
    from app.extensions import db
    return jsonify(
        templates=[{"id": x.id, "bank_code": x.bank_code, "name": x.name, "active": x.active} for x in db.session.query(ImportTemplate).all()],
        rules=[{"id": x.id, "pattern": x.pattern, "category_id": x.category_id, "priority": x.priority, "active": x.active} for x in db.session.query(CategorizationRule).all()],
    )


@admin_bp.patch("/import-config/<kind>/<int:object_id>")
@admin_required
def toggle_import_config(kind, object_id):
    model = ImportTemplate if kind == "template" else CategorizationRule if kind == "rule" else None
    if not model:
        abort(404)
    item = service.toggle(model, object_id, json_body().get("active"))
    return jsonify(id=item.id, active=item.active)


@admin_bp.get("/operations")
@admin_required
def operations():
    return jsonify(service.operations())


@admin_bp.get("/audit-logs")
@admin_required
def audit_logs():
    page = service.audit_logs(request.args.get("page", 1, type=int))
    return jsonify(items=[{"id": x.id, "action": x.action, "created_at": x.created_at.isoformat()} for x in page.items], total=page.total)
