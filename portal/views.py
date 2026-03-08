import os
import json
from pathlib import Path
from functools import wraps
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, session, current_app, jsonify, send_from_directory
)
from werkzeug.utils import secure_filename
from .database import (
    get_questionnaire, save_questionnaire, get_uploads,
    save_upload, delete_upload, get_user_by_id
)
from .questionnaire import (
    QUESTIONNAIRE_SECTIONS, get_required_documents,
    get_section_for_filing_status
)

portal_bp = Blueprint("portal", __name__)

TAX_YEARS = [2022, 2023, 2024]
CURRENT_YEAR = 2024


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access the portal.", "error")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def _db_path() -> str:
    return current_app.config["DB_PATH"]


def _upload_folder() -> str:
    return current_app.config["UPLOAD_FOLDER"]


def _allowed_file(filename: str) -> bool:
    allowed = current_app.config.get("ALLOWED_EXTENSIONS", set())
    ext = Path(filename).suffix.lower()
    return ext in allowed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _year_status(user_id: int, tax_year: int) -> dict:
    """Return status info for a tax year card."""
    qr = get_questionnaire(_db_path(), user_id, tax_year)
    uploads = get_uploads(_db_path(), user_id, tax_year)

    if qr and qr.get("completed"):
        status = "Complete"
        status_class = "badge-success"
    elif qr and qr.get("answers") and qr["answers"] != {}:
        status = "In Progress"
        status_class = "badge-warning"
    else:
        status = "Not Started"
        status_class = "badge-secondary"

    return {
        "year": tax_year,
        "status": status,
        "status_class": status_class,
        "doc_count": len(uploads),
        "questionnaire_started": bool(qr),
        "is_current": tax_year == CURRENT_YEAR,
    }


def _save_upload_file(user_id: int, tax_year: int, category: str, file) -> dict:
    """Save an uploaded file to disk and record in DB. Returns upload record."""
    base_dir = Path(_upload_folder()) / str(user_id) / str(tax_year) / category
    base_dir.mkdir(parents=True, exist_ok=True)

    original_name = file.filename
    safe_name = secure_filename(original_name)
    # Avoid collisions by prepending a short random hex
    import secrets
    unique_prefix = secrets.token_hex(4)
    stored_name = f"{unique_prefix}_{safe_name}"
    dest = base_dir / stored_name
    file.save(str(dest))

    upload_id = save_upload(
        db_path=_db_path(),
        user_id=user_id,
        tax_year=tax_year,
        category=category,
        filename=stored_name,
        original_name=original_name,
    )
    return {"id": upload_id, "filename": stored_name, "original_name": original_name}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@portal_bp.route("/")
@login_required
def index():
    return redirect(url_for("portal.dashboard"))


@portal_bp.route("/dashboard")
@login_required
def dashboard():
    user_id = session["user_id"]
    years_data = [_year_status(user_id, y) for y in TAX_YEARS]
    return render_template("portal/dashboard.html", years=years_data, current_year=CURRENT_YEAR)


@portal_bp.route("/year/<int:year>")
@login_required
def year_detail(year: int):
    if year not in TAX_YEARS:
        flash("Invalid tax year.", "error")
        return redirect(url_for("portal.dashboard"))

    user_id = session["user_id"]
    qr = get_questionnaire(_db_path(), user_id, year)
    uploads = get_uploads(_db_path(), user_id, year)
    answers = qr["answers"] if qr else {}
    filing_status = session.get("filing_status", "single")
    docs = get_required_documents(answers, filing_status)

    # Group uploads by category
    uploads_by_cat = {}
    for u in uploads:
        uploads_by_cat.setdefault(u["category"], []).append(u)

    for doc in docs:
        doc["uploads"] = uploads_by_cat.get(doc["category"], [])
        doc["uploaded"] = len(doc["uploads"]) > 0

    status = _year_status(user_id, year)

    return render_template(
        "portal/checklist.html",
        year=year,
        docs=docs,
        status=status,
        questionnaire_complete=bool(qr and qr.get("completed")),
        answers=answers,
    )


@portal_bp.route("/year/<int:year>/questionnaire", methods=["GET", "POST"])
@login_required
def questionnaire(year: int):
    if year not in TAX_YEARS:
        flash("Invalid tax year.", "error")
        return redirect(url_for("portal.dashboard"))

    user_id = session["user_id"]
    filing_status = session.get("filing_status", "single")
    sections = get_section_for_filing_status(QUESTIONNAIRE_SECTIONS, filing_status)
    total_sections = len(sections)

    qr = get_questionnaire(_db_path(), user_id, year)
    saved_answers = qr["answers"] if qr else {}

    if request.method == "POST":
        action = request.form.get("action", "save")
        section_idx = int(request.form.get("section_idx", 0))

        # Collect answers from this section's questions
        section = sections[section_idx]
        new_answers = dict(saved_answers)

        for q in section["questions"]:
            qid = q["id"]
            qtype = q["type"]
            if qtype == "yes_no":
                val = request.form.get(qid, "")
                if val in ("yes", "no"):
                    new_answers[qid] = val
            elif qtype == "dependents":
                # Dependents sent as JSON string
                dep_json = request.form.get(qid + "_json", "[]")
                try:
                    deps = json.loads(dep_json)
                except (json.JSONDecodeError, ValueError):
                    deps = []
                new_answers[qid] = deps
            elif qtype in ("text", "number", "select"):
                val = request.form.get(qid, "").strip()
                if val:
                    new_answers[qid] = val

        next_section_idx = section_idx + 1
        is_last = next_section_idx >= total_sections
        completed = is_last and action == "finish"

        save_questionnaire(_db_path(), user_id, year, new_answers, completed=completed)

        if completed:
            flash("Questionnaire completed! Your document checklist has been updated.", "success")
            return redirect(url_for("portal.year_detail", year=year))
        elif action == "next" and not is_last:
            return redirect(url_for("portal.questionnaire", year=year, section=next_section_idx))
        elif action == "back" and section_idx > 0:
            return redirect(url_for("portal.questionnaire", year=year, section=section_idx - 1))
        else:
            flash("Progress saved.", "success")
            return redirect(url_for("portal.questionnaire", year=year, section=section_idx))

    # GET — render the requested section
    try:
        section_idx = int(request.args.get("section", 0))
        section_idx = max(0, min(section_idx, total_sections - 1))
    except (ValueError, TypeError):
        section_idx = 0

    section = sections[section_idx]
    is_last = (section_idx + 1) >= total_sections

    return render_template(
        "portal/questionnaire.html",
        year=year,
        sections=sections,
        section=section,
        section_idx=section_idx,
        total_sections=total_sections,
        is_last=is_last,
        answers=saved_answers,
        filing_status=filing_status,
    )


@portal_bp.route("/year/<int:year>/checklist")
@login_required
def checklist(year: int):
    return redirect(url_for("portal.year_detail", year=year))


@portal_bp.route("/year/<int:year>/upload/<category>", methods=["POST"])
@login_required
def upload_file(year: int, category: str):
    if year not in TAX_YEARS:
        return jsonify({"error": "Invalid tax year"}), 400

    if "file" not in request.files:
        flash("No file selected.", "error")
        return redirect(url_for("portal.year_detail", year=year))

    file = request.files["file"]
    if not file or file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("portal.year_detail", year=year))

    if not _allowed_file(file.filename):
        flash(f"File type not allowed. Allowed types: PDF, JPG, PNG, TIFF, DOC, DOCX, XLS, XLSX, CSV.", "error")
        return redirect(url_for("portal.year_detail", year=year))

    try:
        upload = _save_upload_file(session["user_id"], year, category, file)
        flash(f"File '{file.filename}' uploaded successfully.", "success")
    except Exception as exc:
        flash(f"Upload failed: {exc}", "error")

    return redirect(url_for("portal.year_detail", year=year))


@portal_bp.route("/year/<int:year>/upload/<int:upload_id>/delete", methods=["POST"])
@login_required
def delete_upload_file(year: int, upload_id: int):
    user_id = session["user_id"]
    record = delete_upload(_db_path(), upload_id, user_id)

    if record:
        # Remove from disk
        try:
            file_path = (
                Path(_upload_folder())
                / str(user_id)
                / str(record["tax_year"])
                / record["category"]
                / record["filename"]
            )
            if file_path.exists():
                file_path.unlink()
        except Exception:
            pass
        flash(f"File '{record['original_name']}' deleted.", "success")
    else:
        flash("File not found or you do not have permission to delete it.", "error")

    return redirect(url_for("portal.year_detail", year=year))
