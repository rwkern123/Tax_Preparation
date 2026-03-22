import json
from pathlib import Path
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, current_app, jsonify, flash,
)
from .auth import login_required
from .database import (
    get_preparer_client_list,
    get_parsed_documents,
    get_parsed_document_by_upload_id,
    reparse_document,
    reparse_document_azure,
)

preparer_bp = Blueprint(
    "preparer",
    __name__,
    url_prefix="/preparer",
    static_folder="static",
    static_url_path="/static",
)

def _tax_year_context() -> dict:
    site_cfg = current_app.config.get("SITE_CONFIG", {})
    current = site_cfg.get("tax_year", 2024)
    years = list(range(current - 2, current + 1))
    return {"tax_years": years, "current_year": current}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _portal_db() -> str:
    return current_app.config["PORTAL_DB_PATH"]


def _preparer_db() -> str:
    return current_app.config["PREPARER_DB_PATH"]


def _build_doc_status(
    expected_docs: list[dict],
    uploads: list[dict],
    parsed_docs: list[dict],
) -> list[dict]:
    """Cross-reference expected docs (from questionnaire) vs uploads vs parsed results."""
    parsed_by_upload = {p["upload_id"]: p for p in parsed_docs}
    uploads_by_cat: dict[str, list] = {}
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
                "upload_id":    u["id"],
                "original_name": u["original_name"],
                "uploaded_at":  u["uploaded_at"],
                "parsed":       bool(parsed and parsed["parsing_status"] == "done"),
                "pending":      bool(parsed and parsed["parsing_status"] == "pending"),
                "failed":       bool(parsed and parsed["parsing_status"] == "failed"),
                "doc_type":     parsed["doc_type"] if parsed else None,
                "confidence":   parsed["confidence"] if parsed else None,
                "flag_count":   len(parsed["flags_json"]) if parsed else 0,
                "parse_error":  parsed["parse_error"] if parsed else None,
            })

        result.append({
            "category":  cat,
            "label":     doc["label"],
            "required":  doc["required"],
            "uploaded":  bool(cat_uploads),
            "uploads":   rows,
        })
    return result


def _build_follow_up_questions(flags: list[dict], questionnaire: dict | None) -> list[str]:
    """Generate human-readable follow-up questions from flags and questionnaire gaps."""
    questions = []
    seen = set()

    for f in flags:
        ftype = f.get("type")
        msg = f.get("message", "")
        key = (ftype, f.get("field"))
        if key in seen:
            continue
        seen.add(key)

        if ftype == "low_confidence":
            questions.append(
                "Please double-check the values on your uploaded document — "
                "our system had difficulty reading it clearly."
            )
        elif ftype == "missing_field":
            field = f.get("field", "a required field")
            questions.append(
                f"We were unable to read '{field}' from one of your documents. "
                "Please provide this value directly."
            )
        elif ftype == "unclassified":
            questions.append(
                "We received a document we could not identify. "
                "Please confirm what this document is and re-upload if needed."
            )
        elif ftype == "parse_error":
            questions.append(
                "One of your documents could not be processed. "
                "Please re-upload it or provide the information manually."
            )

    return questions


def _compute_yoy_comparison(
    current_docs: list[dict],
    prior_docs: list[dict],
) -> list[dict]:
    """
    Build a field-level comparison table between two years.
    Returns list of {label, current, prior, delta_pct, highlight} dicts.
    """
    THRESHOLD = 0.20  # 20% change triggers highlight

    def _sum_field(docs: list[dict], doc_type: str, field: str) -> float | None:
        total = None
        for d in docs:
            records = d.get("extracted_json", {}).get(doc_type, [])
            for rec in records:
                val = rec.get(field)
                if val is not None:
                    total = (total or 0.0) + val
        return total

    comparisons = [
        ("W-2 Wages (Box 1)",          "w2",            "box1_wages"),
        ("Federal Withheld (Box 2)",    "w2",            "box2_fed_withholding"),
        ("SS Wages (Box 3)",            "w2",            "box3_ss_wages"),
        ("Medicare Wages (Box 5)",      "w2",            "box5_medicare_wages"),
        ("Ordinary Dividends",          "brokerage_1099","div_ordinary"),
        ("Qualified Dividends",         "brokerage_1099","div_qualified"),
        ("Interest Income",             "brokerage_1099","int_interest_income"),
        ("1099-B Proceeds",             "brokerage_1099","b_summary"),
        ("Mortgage Interest",           "form_1098",     "mortgage_interest_received"),
        ("Real Estate Taxes",           "form_1098",     "real_estate_taxes"),
    ]

    rows = []
    for label, doc_type, field in comparisons:
        if field == "b_summary":
            # Special case — nested dict
            curr = None
            for d in current_docs:
                for rec in d.get("extracted_json", {}).get("brokerage_1099", []):
                    v = (rec.get("b_summary") or {}).get("proceeds")
                    if v is not None:
                        curr = (curr or 0.0) + v
            prior = None
            for d in prior_docs:
                for rec in d.get("extracted_json", {}).get("brokerage_1099", []):
                    v = (rec.get("b_summary") or {}).get("proceeds")
                    if v is not None:
                        prior = (prior or 0.0) + v
        else:
            curr  = _sum_field(current_docs, doc_type, field)
            prior = _sum_field(prior_docs,   doc_type, field)

        if curr is None and prior is None:
            continue

        delta_pct = None
        highlight = False
        if curr is not None and prior is not None and prior != 0:
            delta_pct = (curr - prior) / abs(prior)
            highlight = abs(delta_pct) > THRESHOLD

        rows.append({
            "label":     label,
            "current":   curr,
            "prior":     prior,
            "delta_pct": delta_pct,
            "highlight": highlight,
        })

    return rows


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@preparer_bp.route("/")
@login_required
def client_list():
    ctx = _tax_year_context()
    year = int(request.args.get("year", ctx["current_year"]))
    clients = get_preparer_client_list(
        portal_db=_portal_db(),
        preparer_db=_preparer_db(),
        tax_year=year,
    )
    return render_template(
        "preparer/client_list.html",
        clients=clients,
        year=year,
        tax_years=ctx["tax_years"],
    )


@preparer_bp.route("/client/<int:user_id>")
@login_required
def client_detail(user_id: int):
    ctx          = _tax_year_context()
    year         = int(request.args.get("year", ctx["current_year"]))
    compare_year = int(request.args.get("compare_year", 0)) or None

    from portal.database import get_user_by_id, get_questionnaire, get_uploads
    from portal.questionnaire import get_required_documents

    user        = get_user_by_id(_portal_db(), user_id)
    if not user:
        flash("Client not found.", "error")
        return redirect(url_for("preparer.client_list"))

    qr          = get_questionnaire(_portal_db(), user_id, year)
    uploads     = get_uploads(_portal_db(), user_id, year)
    parsed_docs = get_parsed_documents(_preparer_db(), user_id, year)

    answers       = qr["answers"] if qr else {}
    filing_status = user.get("filing_status", "single")
    expected_docs = get_required_documents(answers, filing_status)
    doc_status    = _build_doc_status(expected_docs, uploads, parsed_docs)

    # Flatten all flags across parsed docs
    all_flags: list[dict] = []
    for pd in parsed_docs:
        for f in pd.get("flags_json", []):
            f_copy = dict(f)
            f_copy["document"] = pd["original_name"]
            f_copy["upload_id"] = pd["upload_id"]
            all_flags.append(f_copy)

    # Sort: errors first, then warnings, then info
    severity_order = {"error": 0, "warning": 1, "info": 2}
    all_flags.sort(key=lambda f: severity_order.get(f.get("severity", "info"), 2))

    follow_up = _build_follow_up_questions(all_flags, qr)

    # Prior-year comparison
    prior_parsed = None
    yoy_rows     = None
    if compare_year:
        prior_parsed = get_parsed_documents(_preparer_db(), user_id, compare_year)
        yoy_rows     = _compute_yoy_comparison(parsed_docs, prior_parsed)

    from . import site_config
    from portal.questionnaire import QUESTIONNAIRE_SECTIONS, get_section_for_filing_status
    cfg = site_config.load()
    azure_configured = bool(
        cfg.get("azure_enabled")
        and cfg.get("azure_endpoint")
        and cfg.get("azure_api_key")
    )
    filing_status = user.get("filing_status", "single")
    questionnaire_sections = get_section_for_filing_status(QUESTIONNAIRE_SECTIONS, filing_status)

    return render_template(
        "preparer/client_detail.html",
        user=user,
        year=year,
        compare_year=compare_year,
        tax_years=ctx["tax_years"],
        doc_status=doc_status,
        parsed_docs=parsed_docs,
        all_flags=all_flags,
        follow_up=follow_up,
        questionnaire=qr,
        questionnaire_sections=questionnaire_sections,
        yoy_rows=yoy_rows,
        azure_configured=azure_configured,
    )


@preparer_bp.route("/client/<int:user_id>/reparse/<int:upload_id>", methods=["POST"])
@login_required
def reparse(user_id: int, upload_id: int):
    use_ocr = request.form.get("ocr") == "1"
    reparse_document(_preparer_db(), upload_id, use_ocr=use_ocr)
    year = int(request.form.get("year", _tax_year_context()["current_year"]))
    flash("Document re-parsed.", "success")
    return redirect(url_for("preparer.client_detail", user_id=user_id, year=year))


@preparer_bp.route("/client/<int:user_id>/azure-enhance/<int:upload_id>", methods=["POST"])
@login_required
def azure_enhance(user_id: int, upload_id: int):
    from . import site_config
    cfg = site_config.load()
    endpoint = cfg.get("azure_endpoint", "")
    api_key  = cfg.get("azure_api_key", "")
    year     = int(request.form.get("year", _tax_year_context()["current_year"]))

    if not (cfg.get("azure_enabled") and endpoint and api_key):
        flash("Azure is not configured. Please update Settings first.", "error")
        return redirect(url_for("preparer.client_detail", user_id=user_id, year=year))

    try:
        reparse_document_azure(_preparer_db(), upload_id, endpoint=endpoint, api_key=api_key)
        flash("Document enhanced with Azure Document Intelligence.", "success")
    except Exception as exc:
        flash(f"Azure enhancement failed: {exc}", "error")

    return redirect(url_for("preparer.client_detail", user_id=user_id, year=year))


# ---------------------------------------------------------------------------
# Preparer-side file upload (on behalf of client)
# ---------------------------------------------------------------------------

@preparer_bp.route("/client/<int:user_id>/upload/<int:year>/<category>", methods=["POST"])
@login_required
def upload_for_client(user_id: int, year: int, category: str):
    import secrets
    from pathlib import Path as _Path
    from werkzeug.utils import secure_filename
    from portal.database import save_upload

    if "file" not in request.files or request.files["file"].filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("preparer.client_detail", user_id=user_id, year=year))

    file = request.files["file"]
    allowed = current_app.config.get("ALLOWED_EXTENSIONS", set())
    if _Path(file.filename).suffix.lower() not in allowed:
        flash("File type not allowed.", "error")
        return redirect(url_for("preparer.client_detail", user_id=user_id, year=year))

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    dest_dir = _Path(upload_folder) / str(user_id) / str(year) / category
    dest_dir.mkdir(parents=True, exist_ok=True)

    original_name = file.filename
    stored_name = f"{secrets.token_hex(4)}_{secure_filename(original_name)}"
    dest = dest_dir / stored_name
    file.save(str(dest))

    upload_id = save_upload(
        db_path=_portal_db(),
        user_id=user_id,
        tax_year=year,
        category=category,
        filename=stored_name,
        original_name=original_name,
    )

    # Parse if supported
    _ext = dest.suffix.lower()
    if _ext == ".pdf":
        try:
            from preparer.parser_bridge import parse_uploaded_file
            from preparer.database import upsert_parsed_document
            result = parse_uploaded_file(str(dest), use_ocr=False)
            upsert_parsed_document(
                db_path=_preparer_db(),
                upload_id=upload_id,
                user_id=user_id,
                tax_year=year,
                category=category,
                original_name=original_name,
                file_path=str(dest),
                doc_type=result["doc_type"],
                confidence=result["confidence"],
                parsing_status=result["parsing_status"],
                parse_error=result["parse_error"],
                extracted_json=result["extracted"],
                drake_json=result["drake"],
                flags=result["flags"],
            )
        except Exception:
            pass
    elif _ext in (".csv", ".xml"):
        try:
            from preparer.database import upsert_parsed_document
            from preparer.parser_bridge import _to_drake_fields, _generate_flags
            from dataclasses import asdict
            content = dest.read_text(encoding="utf-8", errors="replace")
            if _ext == ".csv":
                from src.extract.brokerage_1099_csv import parse_brokerage_1099_csv
                summary, trades = parse_brokerage_1099_csv(content, source_file=original_name)
            else:
                from src.extract.brokerage_1099_xml import parse_brokerage_1099_xml
                summary, trades = parse_brokerage_1099_xml(content, source_file=original_name)
            extracted = {
                "brokerage_1099": [asdict(summary)],
                "brokerage_1099_trades": [asdict(t) for t in trades],
            }
            doc_type = "brokerage_1099"
            confidence = 1.0
            drake = _to_drake_fields(doc_type, extracted)
            flags = _generate_flags(doc_type, confidence, extracted)
            upsert_parsed_document(
                db_path=_preparer_db(),
                upload_id=upload_id,
                user_id=user_id,
                tax_year=year,
                category=category,
                original_name=original_name,
                file_path=str(dest),
                doc_type=doc_type,
                confidence=confidence,
                parsing_status="done",
                parse_error=None,
                extracted_json=extracted,
                drake_json=drake,
                flags=flags,
            )
        except Exception:
            pass

    flash(f"'{original_name}' uploaded.", "success")
    return redirect(url_for("preparer.client_detail", user_id=user_id, year=year))


# ---------------------------------------------------------------------------
# Preparer-side questionnaire editing (on behalf of client)
# ---------------------------------------------------------------------------

@preparer_bp.route("/client/<int:user_id>/questionnaire/<int:year>", methods=["GET"])
@login_required
def edit_questionnaire(user_id: int, year: int):
    from portal.database import get_user_by_id, get_questionnaire
    from portal.questionnaire import QUESTIONNAIRE_SECTIONS, get_section_for_filing_status

    user = get_user_by_id(_portal_db(), user_id)
    if not user:
        flash("Client not found.", "error")
        return redirect(url_for("preparer.client_list"))

    filing_status = user.get("filing_status", "single")
    sections = get_section_for_filing_status(QUESTIONNAIRE_SECTIONS, filing_status)
    qr = get_questionnaire(_portal_db(), user_id, year)
    answers = qr["answers"] if qr else {}

    return render_template(
        "preparer/questionnaire_edit.html",
        user=user,
        year=year,
        sections=sections,
        answers=answers,
    )


@preparer_bp.route("/client/<int:user_id>/questionnaire/<int:year>", methods=["POST"])
@login_required
def save_questionnaire_for_client(user_id: int, year: int):
    import json as _json
    from portal.database import get_user_by_id, get_questionnaire, save_questionnaire
    from portal.questionnaire import QUESTIONNAIRE_SECTIONS, get_section_for_filing_status

    user = get_user_by_id(_portal_db(), user_id)
    if not user:
        flash("Client not found.", "error")
        return redirect(url_for("preparer.client_list"))

    filing_status = user.get("filing_status", "single")
    sections = get_section_for_filing_status(QUESTIONNAIRE_SECTIONS, filing_status)

    qr = get_questionnaire(_portal_db(), user_id, year)
    answers = dict(qr["answers"]) if qr else {}

    for section in sections:
        for q in section["questions"]:
            qid = q["id"]
            qtype = q.get("type", "yes_no")
            if qtype == "yes_no":
                val = request.form.get(qid, "")
                if val in ("yes", "no"):
                    answers[qid] = val
            elif qtype == "dependents":
                dep_json = request.form.get(qid + "_json", "[]")
                try:
                    answers[qid] = _json.loads(dep_json)
                except (ValueError, _json.JSONDecodeError):
                    answers[qid] = []
            elif qtype in ("text", "number", "select"):
                val = request.form.get(qid, "").strip()
                if val:
                    answers[qid] = val

    completed = request.form.get("action") == "complete"
    save_questionnaire(_portal_db(), user_id, year, answers, completed=completed)
    flash("Questionnaire saved.", "success")
    return redirect(url_for("preparer.client_detail", user_id=user_id, year=year))


# ---------------------------------------------------------------------------
# File viewer
# ---------------------------------------------------------------------------

@preparer_bp.route("/uploads/<int:upload_id>")
@login_required
def view_upload(upload_id: int):
    from flask import send_file
    doc = get_parsed_document_by_upload_id(_preparer_db(), upload_id)
    if not doc or not doc.get("file_path"):
        flash("File not found or not available for this document.", "error")
        return redirect(request.referrer or url_for("preparer.client_list"))
    file_path = Path(doc["file_path"])
    if not file_path.exists():
        flash(f"File not found on disk: {file_path.name}", "error")
        return redirect(request.referrer or url_for("preparer.client_list"))
    return send_file(file_path, as_attachment=False, download_name=doc["original_name"])


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@preparer_bp.route("/add-client", methods=["GET"])
@login_required
def add_client():
    return render_template("preparer/add_client.html")


@preparer_bp.route("/add-client", methods=["POST"])
@login_required
def add_client_save():
    from portal.database import create_user, create_spouse, get_user_by_email
    from werkzeug.security import generate_password_hash

    first         = request.form.get("first_name", "").strip()
    last          = request.form.get("last_name", "").strip()
    filing_status = request.form.get("filing_status", "single")
    phone         = request.form.get("phone", "").strip()
    email         = request.form.get("email", "").strip()

    if not first or not last:
        flash("First name and last name are required.", "error")
        return redirect(url_for("preparer.add_client"))

    if not email:
        email = f"{first.lower()}.{last.lower()}@preparer.local"

    if get_user_by_email(_portal_db(), email):
        flash("A client with that email already exists.", "error")
        return redirect(url_for("preparer.add_client"))

    pw_hash = generate_password_hash("changeme")
    user_id = create_user(
        _portal_db(), email=email, phone=phone, password_hash=pw_hash,
        first_name=first, last_name=last, dob="", ssn="",
        address="", city="", state="", zip_code="",
        filing_status=filing_status, two_fa_method="email",
    )

    if filing_status in ("mfj", "mfs"):
        sp_first = request.form.get("spouse_first_name", "").strip()
        sp_last  = request.form.get("spouse_last_name", last).strip()
        if sp_first:
            create_spouse(_portal_db(), user_id, sp_first, sp_last, dob="", ssn="")

    flash(f"Client {first} {last} added.", "success")
    return redirect(url_for("preparer.client_detail", user_id=user_id))


@preparer_bp.route("/import-clients", methods=["POST"])
@login_required
def import_clients():
    from . import site_config
    from .folder_import import import_clients_from_folder
    cfg = site_config.load()
    root_folder = cfg.get("root_folder", "").strip()
    if not root_folder:
        flash("Client Folder Root is not set. Please update Settings first.", "error")
        return redirect(url_for("preparer.settings"))
    result = import_clients_from_folder(root_folder, _portal_db())
    msg = f"Imported {result['imported']} client(s), skipped {result['skipped']} already present."
    if result["errors"]:
        msg += " Errors: " + "; ".join(result["errors"])
        flash(msg, "warning")
    else:
        flash(msg, "success")
    return redirect(url_for("preparer.client_list"))


@preparer_bp.route("/settings", methods=["GET"])
@login_required
def settings():
    from . import site_config
    cfg = site_config.load()
    return render_template("preparer/settings.html", cfg=cfg)


@preparer_bp.route("/settings", methods=["POST"])
@login_required
def settings_save():
    from . import site_config
    site_config.save({
        "tax_year":       int(request.form.get("tax_year", 2024)),
        "root_folder":    request.form.get("root_folder", "").strip(),
        "azure_endpoint": request.form.get("azure_endpoint", "").strip(),
        "azure_api_key":  request.form.get("azure_api_key", "").strip(),
        "azure_enabled":  request.form.get("azure_enabled") == "1",
    })
    flash("Settings saved.", "success")
    return redirect(url_for("preparer.settings"))


