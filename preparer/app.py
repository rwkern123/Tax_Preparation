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

    app.secret_key = os.environ.get("PREPARER_SECRET_KEY") or secrets.token_hex(32)

    portal_data = Path(__file__).parent.parent / "portal_data"
    app.config["PORTAL_DB_PATH"]    = str(portal_data / "portal.db")
    app.config["PREPARER_DB_PATH"]  = str(portal_data / "preparer.db")
    app.config["UPLOAD_FOLDER"]     = str(portal_data / "uploads")
    app.config["ALLOWED_EXTENSIONS"] = {
        ".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff",
        ".doc", ".docx", ".xls", ".xlsx", ".csv", ".xml"
    }
    # Set via env var PREPARER_PASSWORD before first run
    app.config["PREPARER_PASSWORD"] = os.environ.get("PREPARER_PASSWORD", "changeme")

    # Load persistent site config (root folder, tax year, Azure credentials)
    from .site_config import load as load_site_config
    site_cfg = load_site_config()
    app.config["SITE_CONFIG"] = site_cfg

    if config:
        app.config.update(config)

    from .database import init_preparer_db
    init_preparer_db(app.config["PREPARER_DB_PATH"])

    from .auth import auth_bp
    from .views import preparer_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(preparer_bp)

    @app.route("/")
    def root():
        from flask import redirect, url_for
        return redirect(url_for("preparer.client_list"))

    # Template filters
    @app.template_filter("fmt_amount")
    def fmt_amount(value):
        if value is None:
            return "—"
        try:
            return f"${float(value):,.2f}"
        except (TypeError, ValueError):
            return str(value)

    # Template globals
    def holding_duration(date_acquired, date_sold):
        """Return human-readable holding period duration, or 'Various'."""
        if not date_acquired or date_acquired.strip().lower() in ("various", "var", "n/a", ""):
            return "Various"
        from datetime import datetime
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
            try:
                d1 = datetime.strptime(date_acquired.strip(), fmt)
                d2 = datetime.strptime((date_sold or "").strip(), fmt)
                days = (d2 - d1).days
                if days < 0:
                    return "—"
                years, rem = divmod(days, 365)
                months = rem // 30
                parts = []
                if years:
                    parts.append(f"{years}y")
                if months:
                    parts.append(f"{months}m")
                if not parts:
                    parts.append(f"{days}d")
                return " ".join(parts)
            except (ValueError, AttributeError):
                continue
        return date_acquired

    app.jinja_env.globals["holding_duration"] = holding_duration

    return app
