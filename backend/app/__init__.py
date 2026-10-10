from pathlib import Path

from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

db = SQLAlchemy()


def create_app():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path, override=False)

    app = Flask(__name__)

    from app.config import Config
    app.config.from_object(Config)

    db.init_app(app)

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
        allowed_origins = {"http://localhost:5173", "http://127.0.0.1:5173"}
        if origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers.add("Vary", "Origin")
        return response

    return app
