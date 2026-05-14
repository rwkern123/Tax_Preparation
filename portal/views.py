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
    save_upload, delete_upload, get_user_by_id,
    save_schedule_c_part, get_schedule_c_responses,
    get_schedule_c_progress, get_schedule_c_business_count,
)
from .questionnaire import (
    QUESTIONNAIRE_SECTIONS, get_required_documents,
    get_section_for_filing_status
)
from .schedule_c_interview import (
    SCHEDULE_C_PARTS, get_part_by_id, get_part_ids,
    get_inline_doc_hints, compute_net_profit, get_preparer_flags,
    IRS_INSTRUCTIONS, PUB_REFERENCES,
)

portal_bp = Blueprint("portal", __name__)

TAX_YEARS = [2022, 2023, 2024, 2025]
CURRENT_YEAR = 2025


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


def _preparer_db_path() -> str:
    return current_app.config.get("PREPARER_DB_PATH", "")


def _upload_folder() -> str:
    return current_app.config["UPLOAD_FOLDER"]


def _build_doc_status(expected_docs, uploads, parsed_docs):
    """Same logic as preparer's _build_doc_status — cross-reference expected vs uploaded vs parsed."""
    parsed_by_upload = {p["upload_id"]: p for p in parsed_docs}
    uploads_by_cat: dict = {}
    for u in uploads:
        uploads_by_cat.setdefault(u["category"], []).append(u)

    result = []
    for doc in expected_docs:
        cat = doc["category"]
        cat_uploads = uploads_by_cat.get(cat, [])
        rows = []
        for u in cat_uploads:
            parsed = parsed_by_upload.get(u["id"])
            rows.append({
                "upload_id":     u["id"],
                "original_name": u["original_name"],
                "uploaded_at":   u["uploaded_at"],
                "parsed":        bool(parsed and parsed["parsing_status"] == "done"),
                "pending":       bool(parsed and parsed["parsing_status"] == "pending"),
                "failed":        bool(parsed and parsed["parsing_status"] == "failed"),
                "doc_type":      parsed["doc_type"] if parsed else None,
                "confidence":    parsed["confidence"] if parsed else None,
                "parse_error":   parsed["parse_error"] if parsed else None,
            })
        result.append({
            "category": cat,
            "label":    doc["label"],
            "required": doc.get("required", True),
            "uploaded": bool(cat_uploads),
            "uploads":  rows,
        })
    return result


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
    expected_docs = get_required_documents(answers, filing_status)

    # Pull parse results from preparer.db so client sees parse status
    parsed_docs = []
    preparer_db = _preparer_db_path()
    if preparer_db:
        try:
            from preparer.database import get_parsed_documents
            parsed_docs = get_parsed_documents(preparer_db, user_id, year)
        except Exception:
            pass

    doc_status = _build_doc_status(expected_docs, uploads, parsed_docs)
    status = _year_status(user_id, year)
    questionnaire_sections = get_section_for_filing_status(QUESTIONNAIRE_SECTIONS, filing_status)

    manual_entries = []
    if preparer_db:
        try:
            from preparer.database import get_manual_entries
            manual_entries = get_manual_entries(preparer_db, user_id, year)
        except Exception:
            pass

    charitable_entries = [
        e for e in manual_entries
        if e["category"] in ("charitable_cash", "charitable_noncash")
    ]

    # If there are charitable entries but Charitable_Records isn't in doc_status
    # (because the questionnaire answer wasn't set), inject it so the rows render.
    has_charitable_in_status = any(d["category"] == "Charitable_Records" for d in doc_status)
    if charitable_entries and not has_charitable_in_status:
        doc_status.append({
            "category": "Charitable_Records",
            "label": "Charitable Contribution Records",
            "required": False,
            "uploaded": False,
            "uploads": [],
        })

    schedule_c_progress = {}
    if answers.get("self_employment") == "yes":
        schedule_c_progress = get_schedule_c_progress(_db_path(), user_id, year)

    return render_template(
        "portal/checklist.html",
        year=year,
        doc_status=doc_status,
        status=status,
        questionnaire=qr,
        questionnaire_sections=questionnaire_sections,
        questionnaire_complete=bool(qr and qr.get("completed")),
        answers=answers,
        manual_entries=manual_entries,
        charitable_entries=charitable_entries,
        schedule_c_progress=schedule_c_progress,
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

    qr = get_questionnaire(_db_path(), user_id, year)
    saved_answers = qr["answers"] if qr else {}

    if request.method == "POST":
        action = request.form.get("action", "save")
        new_answers = dict(saved_answers)

        for section in sections:
            for q in section["questions"]:
                qid = q["id"]
                qtype = q.get("type", "yes_no")
                if qtype == "yes_no":
                    val = request.form.get(qid, "")
                    if val in ("yes", "no"):
                        new_answers[qid] = val
                elif qtype == "dependents":
                    dep_json = request.form.get(qid + "_json", "[]")
                    try:
                        new_answers[qid] = json.loads(dep_json)
                    except (json.JSONDecodeError, ValueError):
                        new_answers[qid] = []
                elif qtype in ("text", "number", "select"):
                    val = request.form.get(qid, "").strip()
                    if val:
                        new_answers[qid] = val

        completed = action == "complete"
        save_questionnaire(_db_path(), user_id, year, new_answers, completed=completed)

        if completed:
            flash("Questionnaire completed! Your document checklist has been updated.", "success")
            return redirect(url_for("portal.year_detail", year=year))
        else:
            flash("Progress saved.", "success")
            return redirect(url_for("portal.questionnaire", year=year))

    return render_template(
        "portal/questionnaire.html",
        year=year,
        sections=sections,
        answers=saved_answers,
        filing_status=filing_status,
        questionnaire_complete=bool(qr and qr.get("completed")),
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
        _trigger_parse_on_upload(
            upload_id=upload["id"],
            user_id=session["user_id"],
            tax_year=year,
            category=category,
            original_name=upload["original_name"],
            stored_name=upload["filename"],
        )
    except Exception as exc:
        flash(f"Upload failed: {exc}", "error")

    return redirect(url_for("portal.year_detail", year=year))


def _trigger_parse_on_upload(
    upload_id: int,
    user_id: int,
    tax_year: int,
    category: str,
    original_name: str,
    stored_name: str,
) -> None:
    """Synchronously parse an uploaded PDF and write results to preparer.db.
    Non-PDF files are skipped. Parse failures are stored silently — never shown to the client."""
    file_path = (
        Path(_upload_folder())
        / str(user_id)
        / str(tax_year)
        / category
        / stored_name
    )

    if file_path.suffix.lower() != ".pdf":
        return

    preparer_db = current_app.config.get("PREPARER_DB_PATH")
    if not preparer_db:
        return

    try:
        from preparer.parser_bridge import parse_uploaded_file
        from preparer.database import upsert_parsed_document

        result = parse_uploaded_file(str(file_path), use_ocr=False)
        upsert_parsed_document(
            db_path=preparer_db,
            upload_id=upload_id,
            user_id=user_id,
            tax_year=tax_year,
            category=category,
            original_name=original_name,
            file_path=str(file_path),
            doc_type=result["doc_type"],
            confidence=result["confidence"],
            parsing_status=result["parsing_status"],
            parse_error=result["parse_error"],
            extracted_json=result["extracted"],
            drake_json=result["drake"],
            flags=result["flags"],
        )
    except Exception:
        pass  # Never surface parse failures to the client


@portal_bp.route("/year/<int:year>/charitable/add", methods=["POST"])
@login_required
def save_charitable_entry(year: int):
    if year not in TAX_YEARS:
        flash("Invalid tax year.", "error")
        return redirect(url_for("portal.dashboard"))

    user_id = session["user_id"]
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "charitable_cash")
    try:
        amount = float(request.form.get("amount", "0").replace(",", ""))
    except ValueError:
        amount = 0.0

    if not name or amount <= 0:
        flash("Organization name and a positive amount are required.", "error")
        return redirect(url_for("portal.year_detail", year=year))

    preparer_db = _preparer_db_path()
    if preparer_db:
        try:
            from preparer.database import save_manual_entry
            save_manual_entry(preparer_db, user_id, year, category, name, amount)
            flash(f"Entry '{name}' saved.", "success")
        except Exception as exc:
            flash(f"Could not save entry: {exc}", "error")
    else:
        flash("Preparer database not configured.", "error")

    # Optional supporting file
    file = request.files.get("file")
    if file and file.filename and _allowed_file(file.filename):
        try:
            _save_upload_file(user_id, year, "Charitable_Records", file)
        except Exception:
            pass

    return redirect(url_for("portal.year_detail", year=year))


@portal_bp.route("/year/<int:year>/charitable/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete_charitable_entry(year: int, entry_id: int):
    user_id = session["user_id"]
    preparer_db = _preparer_db_path()
    if preparer_db:
        try:
            from preparer.database import delete_manual_entry
            delete_manual_entry(preparer_db, entry_id, user_id)
            flash("Entry deleted.", "success")
        except Exception as exc:
            flash(f"Could not delete entry: {exc}", "error")
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


# ---------------------------------------------------------------------------
# Schedule C Interview
# ---------------------------------------------------------------------------

@portal_bp.route("/year/<int:year>/schedule-c")
@login_required
def schedule_c_index(year: int):
    """Redirect to the last incomplete part, or intro if no progress yet."""
    if year not in TAX_YEARS:
        flash("Invalid tax year.", "error")
        return redirect(url_for("portal.dashboard"))

    user_id = session["user_id"]
    business_index = int(request.args.get("business", 0))
    responses = get_schedule_c_responses(_db_path(), user_id, year, business_index)
    part_ids = get_part_ids()

    # Find first incomplete part
    for pid in part_ids:
        if not responses.get(pid, {}).get("completed"):
            return redirect(url_for(
                "portal.schedule_c_part",
                year=year, part_id=pid,
                business=business_index,
            ))

    # All parts complete — go to review
    return redirect(url_for("portal.schedule_c_review", year=year, business=business_index))


@portal_bp.route("/year/<int:year>/schedule-c/part/<part_id>", methods=["GET"])
@login_required
def schedule_c_part(year: int, part_id: str):
    if year not in TAX_YEARS:
        flash("Invalid tax year.", "error")
        return redirect(url_for("portal.dashboard"))

    part = get_part_by_id(part_id)
    if not part:
        flash("Invalid interview section.", "error")
        return redirect(url_for("portal.schedule_c_index", year=year))

    user_id = session["user_id"]
    business_index = int(request.args.get("business", 0))
    responses = get_schedule_c_responses(_db_path(), user_id, year, business_index)
    part_ids = get_part_ids()

    # Merge all answers for conditional logic
    all_answers: dict = {}
    for pid in part_ids:
        all_answers.update(responses.get(pid, {}).get("answers", {}))

    current_answers = responses.get(part_id, {}).get("answers", {})
    doc_hints = get_inline_doc_hints(part_id, all_answers)
    uploads = get_uploads(_db_path(), user_id, year)
    uploads_by_cat = {}
    for u in uploads:
        uploads_by_cat.setdefault(u["category"], []).append(u)

    # Build nav with completion state
    nav_parts = []
    for pid in part_ids:
        p = get_part_by_id(pid)
        nav_parts.append({
            "id": pid,
            "title": p["title"],
            "completed": responses.get(pid, {}).get("completed", False),
            "active": pid == part_id,
        })

    # Progress percentage
    completed_count = sum(1 for np in nav_parts if np["completed"])
    progress_pct = int(completed_count / len(part_ids) * 100) if part_ids else 0

    business_count = get_schedule_c_business_count(_db_path(), user_id, year)

    return render_template(
        "portal/schedule_c_interview.html",
        year=year,
        part=part,
        part_id=part_id,
        part_ids=part_ids,
        nav_parts=nav_parts,
        answers=current_answers,
        all_answers=all_answers,
        doc_hints=doc_hints,
        uploads_by_cat=uploads_by_cat,
        progress_pct=progress_pct,
        business_index=business_index,
        business_count=business_count,
    )


@portal_bp.route("/year/<int:year>/schedule-c/save", methods=["POST"])
@login_required
def schedule_c_save(year: int):
    """AJAX auto-save endpoint. Returns JSON."""
    if year not in TAX_YEARS:
        return jsonify({"ok": False, "error": "Invalid year"}), 400

    user_id = session["user_id"]
    data = request.get_json(silent=True) or {}
    part_id = data.get("part_id", "")
    business_index = int(data.get("business_index", 0))
    answers = data.get("answers", {})
    completed = bool(data.get("completed", False))

    if not get_part_by_id(part_id):
        return jsonify({"ok": False, "error": "Invalid part"}), 400

    save_schedule_c_part(_db_path(), user_id, year, business_index, part_id, answers, completed)
    return jsonify({"ok": True})


@portal_bp.route("/year/<int:year>/schedule-c/review")
@login_required
def schedule_c_review(year: int):
    if year not in TAX_YEARS:
        flash("Invalid tax year.", "error")
        return redirect(url_for("portal.dashboard"))

    user_id = session["user_id"]
    business_index = int(request.args.get("business", 0))
    responses = get_schedule_c_responses(_db_path(), user_id, year, business_index)
    part_ids = get_part_ids()

    all_answers: dict = {}
    for pid in part_ids:
        all_answers.update(responses.get(pid, {}).get("answers", {}))

    summary = compute_net_profit(all_answers)
    nav_parts = []
    for pid in part_ids:
        p = get_part_by_id(pid)
        nav_parts.append({
            "id": pid,
            "title": p["title"],
            "completed": responses.get(pid, {}).get("completed", False),
            "active": False,
        })
    completed_count = sum(1 for np in nav_parts if np["completed"])
    progress_pct = int(completed_count / len(part_ids) * 100) if part_ids else 0
    business_count = get_schedule_c_business_count(_db_path(), user_id, year)

    return render_template(
        "portal/schedule_c_review.html",
        year=year,
        all_answers=all_answers,
        summary=summary,
        nav_parts=nav_parts,
        progress_pct=progress_pct,
        business_index=business_index,
        business_count=business_count,
        parts=SCHEDULE_C_PARTS,
    )


@portal_bp.route("/year/<int:year>/schedule-c/add-business", methods=["POST"])
@login_required
def schedule_c_add_business(year: int):
    if year not in TAX_YEARS:
        flash("Invalid tax year.", "error")
        return redirect(url_for("portal.dashboard"))

    user_id = session["user_id"]
    new_index = get_schedule_c_business_count(_db_path(), user_id, year)
    return redirect(url_for(
        "portal.schedule_c_part",
        year=year,
        part_id="intro",
        business=new_index,
    ))
