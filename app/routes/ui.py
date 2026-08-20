from pathlib import Path

from flask import Blueprint, send_from_directory

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
ui_bp = Blueprint("ui", __name__)


@ui_bp.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@ui_bp.get("/<path:filename>")
def assets(filename):
    return send_from_directory(FRONTEND_DIR, filename)
