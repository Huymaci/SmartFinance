from flask import Blueprint, jsonify, session
from flask_login import current_user, login_user, logout_user
from flask_wtf.csrf import generate_csrf

from app.extensions import limiter
from app.services import auth as service

from .helpers import json_body, validation_response

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.get("/privacy-notice")
def privacy_notice():
    return jsonify(
        notice="Dữ liệu chỉ được dùng để quản lý tài chính cá nhân; không quảng cáo, chấm điểm tín dụng hoặc chia sẻ bên thứ ba.",
        consent_default=False,
    )


@auth_bp.get("/csrf")
def csrf_token():
    return jsonify(csrf_token=generate_csrf())


@auth_bp.post("/register")
@limiter.limit("10 per minute")
def register():
    return validation_response(lambda: (jsonify(id=service.register(json_body()).id, message="Đăng ký thành công"), 201))


@auth_bp.post("/login")
@limiter.limit("10 per minute")
def login():
    def action():
        data = json_body()
        user = service.authenticate(data.get("email"), data.get("password"))
        session.clear()
        login_user(user)
        session.permanent = True
        return jsonify(message="Đăng nhập thành công", role=user.role)
    return validation_response(action)


@auth_bp.post("/logout")
def logout():
    if current_user.is_authenticated:
        logout_user()
    session.clear()
    return jsonify(message="Đã đăng xuất")
