from flask import Flask
from pathlib import Path
import os
import secrets


def create_app(config: dict = None) -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    app.secret_key = os.environ.get("PORTAL_SECRET_KEY") or secrets.token_hex(32)
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB max upload

    portal_data = Path(__file__).parent.parent / "portal_data"
    app.config["UPLOAD_FOLDER"] = str(portal_data / "uploads")
    app.config["DB_PATH"] = str(portal_data / "portal.db")
    app.config["SMTP_CONFIG"] = {}  # Populate for email 2FA
    app.config["ALLOWED_EXTENSIONS"] = {
        ".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff",
        ".doc", ".docx", ".xls", ".xlsx", ".csv"
    }

    if config:
        app.config.update(config)

    # Ensure upload directory exists
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    from .database import init_db
    with app.app_context():
        init_db(app.config["DB_PATH"])

    from .auth import auth_bp
    from .views import portal_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(portal_bp)

    return app
