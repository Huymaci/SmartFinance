from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from app.services import budgets as service

from .helpers import json_body, validation_response

budgets_bp = Blueprint("budgets", __name__, url_prefix="/budgets")


def budget_json(item):
    return {"id": item.id, "category_id": item.category_id, "month": item.month.strftime("%Y-%m"), "amount": item.amount}


@budgets_bp.get("")
@login_required
def list_budgets():
    return validation_response(lambda: jsonify(items=[budget_json(item) for item in service.list_budgets(current_user.id, request.args.get("month"))]))


@budgets_bp.put("")
@login_required
def set_budget():
    return validation_response(lambda: jsonify(budget_json(service.set_budget(current_user, json_body()))))


@budgets_bp.post("/copy")
@login_required
def copy_budgets():
    return validation_response(lambda: jsonify(copied=service.copy_previous(current_user, json_body().get("month"))))


@budgets_bp.get("/safe-to-spend")
@login_required
def get_safe_to_spend():
    return validation_response(lambda: jsonify(amount=service.safe_to_spend(current_user.id, request.args.get("month"))))
