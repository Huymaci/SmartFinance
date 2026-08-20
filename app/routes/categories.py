from flask import Blueprint, jsonify
from flask_login import current_user, login_required

from app.services import categories as service

from .helpers import json_body, validation_response

categories_bp = Blueprint("categories", __name__, url_prefix="/categories")


def category_json(item):
    return {"id": item.id, "name": item.name, "nature": item.nature, "parent_id": item.parent_id, "custom": item.owner_id is not None}


@categories_bp.get("")
@login_required
def list_categories():
    return jsonify(items=[category_json(item) for item in service.list_categories(current_user.id)])


@categories_bp.post("")
@login_required
def create_category():
    return validation_response(lambda: (jsonify(category_json(service.create(current_user, json_body()))), 201))


@categories_bp.patch("/<int:category_id>")
@login_required
def rename_category(category_id):
    return validation_response(lambda: jsonify(category_json(service.rename(current_user, category_id, json_body().get("name")))))


@categories_bp.delete("/<int:category_id>")
@login_required
def delete_category(category_id):
    return validation_response(lambda: (service.remove(current_user, category_id, json_body().get("reassign_to")), jsonify(message="Đã xóa và chuyển giao dịch sang category thay thế"))[1])
