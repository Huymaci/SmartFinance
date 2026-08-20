from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from app.services import statistics as service

from .helpers import validation_response

statistics_bp = Blueprint("statistics", __name__, url_prefix="/statistics")


@statistics_bp.get("/dashboard")
@login_required
def dashboard():
    return validation_response(lambda: jsonify(service.dashboard(current_user.id, request.args.get("month"))))


@statistics_bp.get("/breakdown")
@login_required
def breakdown():
    def action():
        items = service.breakdown(current_user.id, request.args.get("date_from"), request.args.get("date_to"))
        return jsonify(items=items, total_expense=sum(item["amount"] for item in items))

    return validation_response(action)


@statistics_bp.get("/trend")
@login_required
def trend():
    return validation_response(lambda: jsonify(items=service.trend(current_user.id, request.args.get("through"))))
