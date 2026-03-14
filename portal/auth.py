import re
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, session, current_app
)
from werkzeug.security import generate_password_hash, check_password_hash
from .database import (
    get_user_by_email, get_user_by_id, create_user,
    create_spouse, save_code, verify_code, update_password
)
from .two_factor import generate_code, send_code

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SSN_RE = re.compile(r"^\d{3}-\d{2}-\d{4}$")
PHONE_RE = re.compile(r"^\d{10,15}$")


def _db_path() -> str:
    return current_app.config["DB_PATH"]


def _smtp_config() -> dict:
    return current_app.config.get("SMTP_CONFIG", {})


def _validate_registration(form) -> list[str]:
    errors = []
    required = [
        ("first_name", "First name"),
        ("last_name", "Last name"),
        ("email", "Email"),
        ("dob", "Date of birth"),
        ("ssn", "SSN"),
        ("filing_status", "Filing status"),
        ("password", "Password"),
        ("confirm_password", "Confirm password"),
    ]
    for field, label in required:
        if not form.get(field, "").strip():
            errors.append(f"{label} is required.")

    email = form.get("email", "").strip()
    if email and not EMAIL_RE.match(email):
        errors.append("Email address is not valid.")

    ssn = form.get("ssn", "").strip()
    if ssn and not SSN_RE.match(ssn):
        errors.append("SSN must be in XXX-XX-XXXX format.")

    phone = re.sub(r"[^\d]", "", form.get("phone", ""))
    if phone and not PHONE_RE.match(phone):
        errors.append("Phone number must contain 10-15 digits.")

    password = form.get("password", "")
    confirm = form.get("confirm_password", "")
    if password and confirm and password != confirm:
        errors.append("Passwords do not match.")
    if password and len(password) < 8:
        errors.append("Password must be at least 8 characters.")

    # Spouse fields required if married
    fs = form.get("filing_status", "")
    if fs in ("mfj", "mfs"):
        for field, label in [
            ("spouse_first_name", "Spouse first name"),
            ("spouse_last_name", "Spouse last name"),
            ("spouse_dob", "Spouse date of birth"),
            ("spouse_ssn", "Spouse SSN"),
        ]:
            if not form.get(field, "").strip():
                errors.append(f"{label} is required for married filing status.")
        sp_ssn = form.get("spouse_ssn", "").strip()
        if sp_ssn and not SSN_RE.match(sp_ssn):
            errors.append("Spouse SSN must be in XXX-XX-XXXX format.")

    return errors


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("portal.dashboard"))

    if request.method == "POST":
        form = request.form
        errors = _validate_registration(form)

        # Check for duplicate email
        if not errors:
            existing = get_user_by_email(_db_path(), form["email"].strip())
            if existing:
                errors.append("An account with that email already exists.")

        if errors:
            for err in errors:
                flash(err, "error")
            return render_template("auth/register.html", form=form)

        # Create user
        phone_digits = re.sub(r"[^\d]", "", form.get("phone", ""))
        user_id = create_user(
            db_path=_db_path(),
            email=form["email"].strip(),
            phone=phone_digits,
            password_hash=generate_password_hash(form["password"]),
            first_name=form["first_name"].strip(),
            last_name=form["last_name"].strip(),
            dob=form["dob"].strip(),
            ssn=form["ssn"].strip(),
            address=form.get("address", "").strip(),
            city=form.get("city", "").strip(),
            state=form.get("state", "").strip(),
            zip_code=form.get("zip", "").strip(),
            filing_status=form["filing_status"],
            two_fa_method=form.get("two_fa_method", "email"),
        )

        # Create spouse if applicable
        if form["filing_status"] in ("mfj", "mfs"):
            create_spouse(
                db_path=_db_path(),
                user_id=user_id,
                first_name=form["spouse_first_name"].strip(),
                last_name=form["spouse_last_name"].strip(),
                dob=form["spouse_dob"].strip(),
                ssn=form["spouse_ssn"].strip(),
            )

        flash("Account created! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form={})


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("portal.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("auth/login.html", email=email)

        user = get_user_by_email(_db_path(), email)
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("auth/login.html", email=email)

        # Generate and send 2FA code
        code = generate_code()
        method = user.get("two_fa_method", "email")
        save_code(_db_path(), user["id"], code, method)
        send_code(user, code, method, _smtp_config())

        # Store pending user in session (not authenticated yet)
        session.clear()
        session["pending_user_id"] = user["id"]
        session["pending_method"] = method
        session["pending_email"] = user["email"]
        session["pending_phone"] = user.get("phone", "")

        return redirect(url_for("auth.verify"))

    return render_template("auth/login.html", email="")


@auth_bp.route("/verify", methods=["GET", "POST"])
def verify():
    pending_id = session.get("pending_user_id")
    if not pending_id:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        entered_code = request.form.get("code", "").strip()

        if not entered_code or len(entered_code) != 6 or not entered_code.isdigit():
            flash("Please enter a valid 6-digit code.", "error")
            return render_template("auth/verify_2fa.html",
                                   method=session.get("pending_method"),
                                   email=session.get("pending_email"),
                                   phone=session.get("pending_phone"))

        if verify_code(_db_path(), pending_id, entered_code):
            user = get_user_by_id(_db_path(), pending_id)
            # Promote to fully authenticated session
            session.pop("pending_user_id", None)
            session.pop("pending_method", None)
            session.pop("pending_email", None)
            session.pop("pending_phone", None)
            session["user_id"] = user["id"]
            session["user_email"] = user["email"]
            session["user_name"] = f"{user['first_name']} {user['last_name']}"
            session["filing_status"] = user["filing_status"]
            flash(f"Welcome back, {user['first_name']}!", "success")
            return redirect(url_for("portal.dashboard"))
        else:
            flash("Invalid or expired code. Please try again.", "error")
            return render_template("auth/verify_2fa.html",
                                   method=session.get("pending_method"),
                                   email=session.get("pending_email"),
                                   phone=session.get("pending_phone"))

    return render_template("auth/verify_2fa.html",
                           method=session.get("pending_method"),
                           email=session.get("pending_email"),
                           phone=session.get("pending_phone"))


@auth_bp.route("/resend-code")
def resend_code():
    pending_id = session.get("pending_user_id")
    if not pending_id:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("auth.login"))

    user = get_user_by_id(_db_path(), pending_id)
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("auth.login"))

    method = user.get("two_fa_method", "email")
    code = generate_code()
    save_code(_db_path(), pending_id, code, method)
    send_code(user, code, method, _smtp_config())
    flash("A new verification code has been sent.", "success")
    return redirect(url_for("auth.verify"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email:
            flash("Email is required.", "error")
            return render_template("auth/forgot_password.html", email="")

        user = get_user_by_email(_db_path(), email)
        if user:
            code = generate_code()
            method = user.get("two_fa_method", "email")
            save_code(_db_path(), user["id"], code, method)
            send_code(user, code, method, _smtp_config())
            session["reset_user_id"] = user["id"]
            session["reset_email"] = user["email"]

        # Always show the same message to avoid email enumeration
        flash("If an account with that email exists, a reset code has been sent.", "success")
        return redirect(url_for("auth.reset_password"))

    return render_template("auth/forgot_password.html", email="")


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    reset_user_id = session.get("reset_user_id")
    if not reset_user_id:
        flash("Please start the password reset process again.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not code or len(code) != 6 or not code.isdigit():
            flash("Please enter a valid 6-digit code.", "error")
            return render_template("auth/reset_password.html", email=session.get("reset_email"))

        if not password or len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("auth/reset_password.html", email=session.get("reset_email"))

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("auth/reset_password.html", email=session.get("reset_email"))

        if not verify_code(_db_path(), reset_user_id, code):
            flash("Invalid or expired code. Please try again.", "error")
            return render_template("auth/reset_password.html", email=session.get("reset_email"))

        update_password(_db_path(), reset_user_id, generate_password_hash(password))
        session.pop("reset_user_id", None)
        session.pop("reset_email", None)
        flash("Password updated successfully. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", email=session.get("reset_email"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))
