from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from app.repositories import TransactionRepository
from app.services import transactions as service
from app.services.common import parse_date

from .helpers import json_body, transaction_json, validation_response

transactions_bp = Blueprint("transactions", __name__, url_prefix="/transactions")


@transactions_bp.get("/<int:transaction_id>")
@login_required
def get_transaction(transaction_id):
    from app.services.common import owned_or_404
    return jsonify(transaction_json(owned_or_404(TransactionRepository.owned(transaction_id, current_user.id))))


@transactions_bp.get("")
@login_required
def list_transactions():
    def action():
        page = TransactionRepository.search(
            current_user.id,
            date_from=parse_date(request.args["date_from"], "date_from") if request.args.get("date_from") else None,
            date_to=parse_date(request.args["date_to"], "date_to") if request.args.get("date_to") else None,
            account_id=request.args.get("account_id", type=int), category_id=request.args.get("category_id", type=int),
            direction=request.args.get("direction"), page=request.args.get("page", 1, type=int), per_page=min(request.args.get("per_page", 20, type=int), 100),
        )
        return jsonify(items=[transaction_json(item) for item in page.items], page=page.page, pages=page.pages, total=page.total)
    return validation_response(action)


@transactions_bp.post("")
@login_required
def create_transaction():
    return validation_response(lambda: (jsonify(transaction_json(service.create(current_user, json_body()))), 201))


@transactions_bp.put("/<int:transaction_id>")
@login_required
def update_transaction(transaction_id):
    return validation_response(lambda: jsonify(transaction_json(service.update(current_user, transaction_id, json_body()))))


@transactions_bp.delete("/<int:transaction_id>")
@login_required
def delete_transaction(transaction_id):
    return validation_response(lambda: (service.delete(current_user, transaction_id), jsonify(message="Đã xóa giao dịch"))[1])
