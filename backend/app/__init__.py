import os
from pathlib import Path

from flask import Flask, request
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

db = SQLAlchemy()
migrate = Migrate()

_LOCAL_VITE_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173"}


def create_app(test_config=None):
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path, override=False)

    app = Flask(__name__)

    from app.config import Config, validate_jwt_secret
    app.config.from_object(Config)
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")
    if test_config is not None:
        app.config.update(test_config)
    validate_jwt_secret(app.config.get("JWT_SECRET_KEY"))

    db.init_app(app)
    migrate.init_app(app, db)

    # Import ORM models so Flask-Migrate/Flask-SQLAlchemy metadata includes tables.
    from app.persistence import models as _persistence_models  # noqa: F401

    from app.routes import bp
    app.register_blueprint(bp)

    from app.auth.errors import AuthError

    @app.errorhandler(AuthError)
    def handle_auth_error(error):
        body = {"error": {"code": error.code, "message": error.message}}
        if error.field is not None:
            body["error"]["field"] = error.field
        return body, error.status_code

    @app.after_request
    def allow_local_vite_origin(response):
        origin = request.headers.get("Origin")
        if origin in _LOCAL_VITE_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PATCH, OPTIONS"
            )
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            response.headers.add("Vary", "Origin")
        return response

    return app
