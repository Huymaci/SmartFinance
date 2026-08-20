from flask import Blueprint, jsonify, send_file
from flask_login import current_user, login_required

from app.extensions import db
from app.models import utcnow
from app.services import auth as auth_service
from app.services.profile import export_data

from .helpers import json_body, validation_response

profile_bp = Blueprint("profile", __name__, url_prefix="/profile")


@profile_bp.get("")
@login_required
def get_profile():
    return jsonify(email=current_user.email, full_name=current_user.full_name, date_of_birth=current_user.date_of_birth.isoformat(), consent=current_user.consent, deletion_requested_at=current_user.deletion_requested_at)


@profile_bp.patch("")
@login_required
def update_profile():
    data = json_body()
    if "full_name" in data:
        if not str(data["full_name"]).strip():
            return jsonify(error="Họ tên không được để trống"), 400
        current_user.full_name = str(data["full_name"]).strip()
    if "consent" in data:
        current_user.consent = data["consent"] is True
    db.session.commit()
    return jsonify(message="Đã cập nhật hồ sơ")


@profile_bp.post("/change-password")
@login_required
def change_password():
    data = json_body()
    return validation_response(lambda: (auth_service.change_password(current_user, data.get("current_password"), data.get("new_password")), jsonify(message="Đã đổi mật khẩu"))[1])


@profile_bp.get("/export")
@login_required
def export():
    return send_file(export_data(current_user), mimetype="application/zip", as_attachment=True, download_name="smartfinance-export.zip")


@profile_bp.post("/deletion-request")
@login_required
def request_deletion():
    current_user.deletion_requested_at = utcnow()
    db.session.commit()
    return jsonify(message="Yêu cầu xóa tài khoản đã được ghi nhận"), 202
