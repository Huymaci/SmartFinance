from flask import Blueprint, jsonify
from flask_login import current_user, login_required

from app.repositories import AccountRepository
from app.services import accounts as service

from .helpers import account_json, json_body, validation_response

accounts_bp = Blueprint("accounts", __name__, url_prefix="/accounts")


@accounts_bp.get("")
@login_required
def list_accounts():
    return jsonify(items=[account_json(item) for item in AccountRepository.list_for(current_user.id)])


@accounts_bp.post("")
@login_required
def create_account():
    return validation_response(lambda: (jsonify(account_json(service.create(current_user, json_body()))), 201))


@accounts_bp.put("/<int:account_id>")
@login_required
def update_account(account_id):
    return validation_response(lambda: jsonify(account_json(service.update(current_user, account_id, json_body()))))


@accounts_bp.delete("/<int:account_id>")
@login_required
def archive_account(account_id):
    return validation_response(lambda: (service.archive(current_user, account_id), jsonify(message="Đã lưu trữ tài khoản"))[1])
