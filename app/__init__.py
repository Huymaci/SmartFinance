import os

from flask import Flask, jsonify

from config import Config

from .extensions import csrf, db, limiter, login_manager, talisman


def create_app(config_object=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)
    csrf.init_app(app)
    talisman.init_app(
        app,
        force_https=app.config["HTTPS_ENABLED"] and not app.testing,
        content_security_policy={"default-src": "'self'", "script-src": "'self'", "style-src": "'self'"},
        frame_options="DENY",
    )

    from .routes.accounts import accounts_bp
    from .routes.admin import admin_bp
    from .routes.alerts import alerts_bp
    from .routes.auth import auth_bp
    from .routes.budgets import budgets_bp
    from .routes.categories import categories_bp
    from .routes.imports import imports_bp
    from .routes.profile import profile_bp
    from .routes.statistics import statistics_bp
    from .routes.transactions import transactions_bp
    from .routes.ui import ui_bp

    for blueprint in (auth_bp, profile_bp, accounts_bp, categories_bp, transactions_bp, imports_bp, budgets_bp, alerts_bp, statistics_bp, admin_bp, ui_bp):
        app.register_blueprint(blueprint)

    @login_manager.unauthorized_handler
    def unauthorized():
        return jsonify(error="Vui lòng đăng nhập để tiếp tục"), 401

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify(error="Yêu cầu không hợp lệ"), 400

    @app.errorhandler(413)
    def too_large(error):
        return jsonify(error="Tệp vượt quá giới hạn 5 MB"), 413

    return app
