from flask import Blueprint, jsonify, request, send_file
from flask_login import current_user, login_required

from app.extensions import db
from app.models import ImportTemplate
from app.services.imports import confirm, error_csv, preview

from .helpers import json_body, validation_response

imports_bp = Blueprint("imports", __name__, url_prefix="/imports")


@imports_bp.get("/templates")
@login_required
def list_templates():
    items = db.session.query(ImportTemplate).filter_by(active=True).order_by(ImportTemplate.bank_code, ImportTemplate.name).all()
    return jsonify(items=[{"id": item.id, "bank_code": item.bank_code, "name": item.name} for item in items])


@imports_bp.post("/preview")
@login_required
def preview_import():
    def action():
        uploaded = request.files.get("file")
        if not uploaded:
            from app.services.common import ValidationError
            raise ValidationError("Thiếu tệp sao kê")
        summary = preview(current_user, int(request.form.get("account_id", 0)), int(request.form.get("template_id", 0)), uploaded)
        return jsonify(summary), 201
    return validation_response(action)


@imports_bp.post("/<int:batch_id>/confirm")
@login_required
def confirm_import(batch_id):
    data = json_body()
    return validation_response(lambda: (jsonify(imported=confirm(current_user, batch_id, data.get("decisions"), data.get("category_overrides"))), 201))


@imports_bp.get("/<int:batch_id>/errors.csv")
@login_required
def download_errors(batch_id):
    return send_file(error_csv(current_user, batch_id), mimetype="text/csv", as_attachment=True, download_name=f"import-{batch_id}-errors.csv")
