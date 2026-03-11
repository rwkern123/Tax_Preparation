from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, current_app, flash,
)

auth_bp = Blueprint("prep_auth", __name__, url_prefix="/auth")


def login_required(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("preparer_authed"):
            return redirect(url_for("prep_auth.login"))
        return f(*args, **kwargs)

    return decorated


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("preparer_authed"):
        return redirect(url_for("preparer.client_list"))

    if request.method == "POST":
        pw = request.form.get("password", "")
        if pw == current_app.config["PREPARER_PASSWORD"]:
            session["preparer_authed"] = True
            session.permanent = True
            return redirect(url_for("preparer.client_list"))
        flash("Incorrect password.", "error")

    return render_template("preparer/login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("prep_auth.login"))
