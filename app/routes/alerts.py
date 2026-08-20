from flask import Blueprint, jsonify
from flask_login import current_user, login_required

from app.services import alerts as service

from .helpers import json_body, validation_response

alerts_bp = Blueprint("alerts", __name__, url_prefix="/alerts")


def alert_json(item):
    return {"id": item.id, "category_id": item.category_id, "kind": item.kind, "severity": item.severity, "explanation": item.explanation, "suggested_action": item.suggested_action, "status": item.status, "triggered_at": item.triggered_at.isoformat()}


@alerts_bp.get("")
@login_required
def inbox():
    return jsonify(items=[alert_json(item) for item in service.list_alerts(current_user.id)])


@alerts_bp.patch("/<int:alert_id>")
@login_required
def update_alert(alert_id):
    return validation_response(lambda: jsonify(alert_json(service.set_status(current_user.id, alert_id, json_body().get("status")))))
