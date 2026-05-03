import io
import json
from pathlib import Path
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, current_app, jsonify, flash, send_file,
)
from .auth import login_required
from .database import (
    get_preparer_client_list,
    get_parsed_documents,
    get_parsed_document_by_upload_id,
    reparse_document,
    reparse_document_azure,
    delete_parsed_document,
    get_manual_entries,
    save_manual_entry,
    delete_manual_entry,
    get_field_overrides,
    save_field_override,
    delete_field_overrides_for_doctype,
    delete_field_override_by_person_field,
)

preparer_bp = Blueprint(
    "preparer",
    __name__,
    url_prefix="/preparer",
    static_folder="static",
    static_url_path="/static",
)


@preparer_bp.app_context_processor
def _inject_sidebar():
    """Inject sidebar client list into all preparer templates."""
    from flask import session, request as _req
    if not session.get("logged_in"):
        return {}
    try:
        ctx = _tax_year_context()
        year = int(_req.args.get("year", ctx["current_year"]))
        clients = get_preparer_client_list(
            portal_db=_portal_db(),
            preparer_db=_preparer_db(),
            tax_year=year,
        )
        return {"sidebar_clients": clients, "sidebar_year": year}
    except Exception:
        return {}


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
    ctx  = _tax_year_context()
    year = int(request.args.get("year", ctx["current_year"]))

    from portal.database import get_user_by_id, get_questionnaire, get_uploads
    from portal.questionnaire import get_required_documents

    user = get_user_by_id(_portal_db(), user_id)
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

    from .form_1040_filler import aggregate_1040_data
    from src.tax_calculator import calculate_tax_from_docs
    manual_entries = get_manual_entries(_preparer_db(), user_id, year)
    form_1040_data = aggregate_1040_data(parsed_docs, user, year, manual_entries=manual_entries)
    field_overrides = get_field_overrides(_preparer_db(), user_id, year)

    num_children = int(user.get("num_dependents") or 0)

    try:
        tax_estimate = calculate_tax_from_docs(
            parsed_docs,
            filing_status=filing_status,
            num_children=num_children,
            estimated_payments=float(user.get("estimated_payments") or 0),
            foreign_tax_credit=float(user.get("foreign_tax_credit") or 0),
            tax_year=year,
            manual_entries=manual_entries,
        )
    except Exception:
        tax_estimate = None

    # Build multi-year columns for Tax Return and Tax Calculator tabs.
    # Pre-index all prior year return docs by their embedded tax year so we can
    # match them to columns regardless of which workspace year they were uploaded under.
    prior_returns_by_year: dict[int, dict] = {}
    all_workspace_years = sorted(ctx["tax_years"])
    for _scan_year in all_workspace_years:
        _scan_docs = parsed_docs if _scan_year == year else get_parsed_documents(_preparer_db(), user_id, _scan_year)
        for doc in _scan_docs:
            for py_rec in (doc.get("extracted_json") or {}).get("prior_year_return", []):
                embedded_year = py_rec.get("year")
                if embedded_year and embedded_year not in prior_returns_by_year:
                    prior_returns_by_year[embedded_year] = py_rec

    # Include all workspace years plus any years covered by prior returns that
    # fall within the two-year lookback window (in case the DB has no parsed docs
    # for a year but we have an uploaded return covering it).
    column_years = set(all_workspace_years) | {y for y in prior_returns_by_year if y >= year - 2}
    year_columns: list[dict] = []
    for y in sorted(column_years):
        y_parsed  = parsed_docs if y == year else get_parsed_documents(_preparer_db(), user_id, y)
        y_manual  = manual_entries if y == year else get_manual_entries(_preparer_db(), user_id, y)

        # For prior years: use the actual filed return if we have one.
        # Fall back to calculating from income docs only if no prior return exists.
        py_return_data: dict | None = None
        if y != year:
            py_return_data = prior_returns_by_year.get(y)

        # Skip columns with no data at all
        if py_return_data is None and not y_parsed and y != year:
            continue

        if py_return_data is not None:
            # Build line dicts directly from the prior year return fields
            py = py_return_data
            src = ["Prior Year Return"]
            main_lines_dict: dict[str, dict] = {
                "1a — W-2 wages, salaries, tips":          {"value": py.get("line_1a_w2_wages"),          "sources": src},
                "1z — Total wages":                         {"value": py.get("line_1z_total_wages"),        "sources": src},
                "2b — Taxable interest":                    {"value": py.get("line_2b_taxable_interest"),   "sources": src},
                "3a — Qualified dividends":                 {"value": py.get("line_3a_qualified_dividends"),"sources": src},
                "3b — Ordinary dividends":                  {"value": py.get("line_3b_ordinary_dividends"), "sources": src},
                "7 — Capital gain or (loss)":              {"value": py.get("line_7_capital_gain_loss"),   "sources": src},
                "9 — Total income":                        {"value": py.get("line_9_total_income"),        "sources": src},
                "11 — Adjusted gross income (AGI)":         {"value": py.get("line_11_agi"),               "sources": src},
                "12 — Standard or itemized deduction":     {"value": py.get("line_12_deductions"),        "sources": src},
                "15 — Taxable income":                     {"value": py.get("line_15_taxable_income"),    "sources": src},
                "16 — Tax":                                {"value": py.get("line_16_tax"),               "sources": src},
                "17 — AMT":                                {"value": py.get("form_6251_amt"),             "sources": src},
                "24 — Total tax":                          {"value": py.get("line_24_total_tax"),         "sources": src},
                "25a — W-2 federal tax withheld":          {"value": py.get("line_25a_w2_withholding"),   "sources": src},
                "25b — 1099 federal tax withheld":         {"value": py.get("line_25b_1099_withholding"), "sources": src},
                "25d — Total federal tax withheld":        {"value": py.get("line_25d_total_withholding"),"sources": src},
                "26 — Estimated tax payments":             {"value": py.get("line_26_estimated_payments"),"sources": src},
                "33 — Total payments":                     {"value": py.get("line_33_total_payments"),    "sources": src},
                "35a — Refund":                            {"value": py.get("line_35a_refund"),           "sources": src},
                "37 — Amount owed":                        {"value": py.get("line_37_amount_owed"),       "sources": src},
            }
            sched_lines_dict: dict[str, dict] = {
                "Sched A 5b — Real estate taxes":         {"value": py.get("sched_a_salt_total"),         "sources": src},
                "Sched A 5e — SALT (capped at $10,000)":  {"value": py.get("sched_a_salt_total"),         "sources": src},
                "Sched A 8a — Home mortgage interest":    {"value": py.get("sched_a_mortgage_interest"),  "sources": src},
                "Sched A 11 — Charitable (cash)":         {"value": py.get("sched_a_charitable_cash"),    "sources": src},
                "Sched A 12 — Charitable (noncash)":      {"value": py.get("sched_a_charitable_noncash"), "sources": src},
                "Sched A 17 — Total itemized deductions": {"value": py.get("sched_a_total_itemized"),     "sources": src},
            }
            y_est = None  # No calculator estimate for prior year return columns
        else:
            y_f1040 = aggregate_1040_data(y_parsed, user, y, manual_entries=y_manual)
            try:
                y_est = (calculate_tax_from_docs(
                    y_parsed,
                    filing_status=filing_status,
                    num_children=num_children,
                    estimated_payments=float(user.get("estimated_payments") or 0),
                    foreign_tax_credit=float(user.get("foreign_tax_credit") or 0),
                    tax_year=y,
                    manual_entries=y_manual,
                ) if y_parsed else None)
            except Exception:
                y_est = None

            # Resolve TaxEstimate fields into lines marked with _est_field
            if y_est:
                _te = y_est
                _te_extra = {
                    "other_taxes":        (_te.niit or 0) + (_te.se_tax or 0) or None,
                    "refund_amount":      _te.refund_or_owed if _te.refund_or_owed >= 0 else None,
                    "owed_amount":        abs(_te.refund_or_owed) if _te.refund_or_owed < 0 else None,
                    "estimated_payments": _te.estimated_payments if _te.estimated_payments else None,
                }
                for ln in (y_f1040 or {}).get("lines", []):
                    ef = ln.get("_est_field")
                    if ef and ln["value"] is None:
                        raw = _te_extra.get(ef, getattr(_te, ef, None))
                        if raw is not None:
                            ln["value"] = raw * ln.get("_est_sign", 1)

            main_lines_dict = {}
            sched_lines_dict = {}
            for ln in (y_f1040 or {}).get("lines", []):
                entry = {"value": ln["value"], "sources": ln.get("sources")}
                if ln.get("sched"):
                    sched_lines_dict[ln["label"]] = entry
                else:
                    main_lines_dict[ln["label"]] = entry

        year_columns.append({
            "year":             y,
            "is_current":       y == year,
            "tax_estimate":     y_est,
            "main_lines_dict":  main_lines_dict,
            "sched_lines_dict": sched_lines_dict,
            "from_prior_return": py_return_data is not None,
        })

    # Reference line order from current year for table headers
    ref_main_lines:  list[dict] = []
    ref_sched_lines: list[dict] = []
    for ln in (form_1040_data or {}).get("lines", []):
        if ln.get("sched") == "A":
            ref_sched_lines.append({"label": ln["label"]})
        elif not ln.get("sched"):
            ref_main_lines.append({"label": ln["label"]})

    return render_template(
        "preparer/client_detail.html",
        user=user,
        year=year,
        tax_years=ctx["tax_years"],
        doc_status=doc_status,
        parsed_docs=parsed_docs,
        all_flags=all_flags,
        follow_up=follow_up,
        questionnaire=qr,
        questionnaire_sections=questionnaire_sections,
        azure_configured=azure_configured,
        form_1040_data=form_1040_data,
        manual_entries=manual_entries,
        charitable_entries=[e for e in manual_entries if e["category"] in ("charitable_cash", "charitable_noncash")],
        field_overrides=field_overrides,
        tax_estimate=tax_estimate,
        year_columns=year_columns,
        ref_main_lines=ref_main_lines,
        ref_sched_lines=ref_sched_lines,
    )


def _apply_clear_fields(db_path: str, user_id: int, year: int, doc_type: str, clear_fields: list[str]) -> None:
    """Delete specific field overrides from 'person.field' strings sent by the UI."""
    for pf in clear_fields:
        if "." in pf:
            person, field = pf.split(".", 1)
            delete_field_override_by_person_field(db_path, user_id, year, doc_type, person, field)


@preparer_bp.route("/client/<int:user_id>/reparse/<int:upload_id>", methods=["POST"])
@login_required
def reparse(user_id: int, upload_id: int):
    use_ocr = request.form.get("ocr") == "1"
    year = int(request.form.get("year", _tax_year_context()["current_year"]))
    doc_type = request.form.get("doc_type", "")
    clear_fields = request.form.getlist("clear_field")
    if clear_fields and doc_type:
        _apply_clear_fields(_preparer_db(), user_id, year, doc_type, clear_fields)
    reparse_document(_preparer_db(), upload_id, use_ocr=use_ocr)
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
    doc_type = request.form.get("doc_type", "")
    clear_fields = request.form.getlist("clear_field")

    if not (cfg.get("azure_enabled") and endpoint and api_key):
        flash("Azure is not configured. Please update Settings first.", "error")
        return redirect(url_for("preparer.client_detail", user_id=user_id, year=year))

    try:
        if clear_fields and doc_type:
            _apply_clear_fields(_preparer_db(), user_id, year, doc_type, clear_fields)
        reparse_document_azure(_preparer_db(), upload_id, endpoint=endpoint, api_key=api_key)
        flash("Document enhanced with Azure Document Intelligence.", "success")
    except Exception as exc:
        flash(f"Azure enhancement failed: {exc}", "error")

    return redirect(url_for("preparer.client_detail", user_id=user_id, year=year))


# ---------------------------------------------------------------------------
# Delete uploaded document
# ---------------------------------------------------------------------------

@preparer_bp.route("/client/<int:user_id>/delete-upload/<int:upload_id>", methods=["POST"])
@login_required
def delete_upload(user_id: int, upload_id: int):
    from portal.database import delete_upload as portal_delete_upload

    parsed = delete_parsed_document(_preparer_db(), upload_id)
    portal_record = portal_delete_upload(_portal_db(), upload_id, user_id)

    # Delete physical file
    file_path = None
    if parsed and parsed.get("file_path"):
        file_path = parsed["file_path"]
    elif portal_record and portal_record.get("filename"):
        upload_folder = current_app.config["UPLOAD_FOLDER"]
        pr = portal_record
        file_path = str(
            Path(upload_folder) / str(user_id) / str(pr["tax_year"]) / pr["category"] / pr["filename"]
        )

    disk_deleted = False
    if file_path:
        try:
            p = Path(file_path)
            if p.exists():
                p.unlink()
                disk_deleted = True
        except Exception:
            pass

    is_ajax = (
        request.is_json
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )
    if is_ajax:
        return jsonify({"success": True, "upload_id": upload_id, "disk_deleted": disk_deleted})

    year = portal_record["tax_year"] if portal_record else _tax_year_context()["current_year"]
    flash("Document deleted.", "success")
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
            result = parse_uploaded_file(str(dest), use_ocr=False, category_hint=category)
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


@preparer_bp.route("/client/<int:user_id>/field-override/<int:year>", methods=["POST"])
@login_required
def save_field_override_route(user_id: int, year: int):
    doc_type = request.form.get("doc_type", "w2").strip()
    # Optional person override (used by 1098 per-lender forms and brokerage per-account forms)
    person_override = request.form.get("person", "").strip()
    for key, raw in request.form.items():
        if key.startswith("tp_"):
            field = key[3:]
            person = person_override or "taxpayer"
            save_field_override(_preparer_db(), user_id, year, doc_type, person, field, raw.strip() or None)
        elif key.startswith("sp_"):
            field = key[3:]
            save_field_override(_preparer_db(), user_id, year, doc_type, "spouse", field, raw.strip() or None)
        elif key.startswith("ba_"):
            # ba_{upload_id}_{field_key} — per-account brokerage override
            rest = key[3:]
            uid_part, field = rest.split("_", 1)
            if uid_part.isdigit():
                person = f"acct_{uid_part}"
                save_field_override(_preparer_db(), user_id, year, doc_type, person, field, raw.strip() or None)
    active_panel = request.form.get("active_panel", "").strip()
    extra = {"panel": active_panel} if active_panel else {}
    return redirect(url_for("preparer.client_detail", user_id=user_id, year=year, **extra) + "#tab-data")


@preparer_bp.route("/client/<int:user_id>/manual-entry/<int:year>", methods=["POST"])
@login_required
def save_manual_entry_route(user_id: int, year: int):
    import secrets
    from pathlib import Path as _Path
    from werkzeug.utils import secure_filename
    from portal.database import save_upload

    name = request.form.get("name", "").strip()
    category = request.form.get("category", "charitable_cash")
    try:
        amount = float(request.form.get("amount", "0").replace(",", ""))
    except ValueError:
        amount = 0.0
    if name and amount > 0:
        save_manual_entry(_preparer_db(), user_id, year, category, name, amount)
        flash(f"Entry '{name}' saved.", "success")
    else:
        flash("Name and a positive amount are required.", "error")
        return redirect(url_for("preparer.client_detail", user_id=user_id, year=year))

    # Optional file upload attached to the same submission
    file = request.files.get("file")
    if file and file.filename:
        allowed = current_app.config.get("ALLOWED_EXTENSIONS", set())
        if _Path(file.filename).suffix.lower() in allowed:
            upload_folder = current_app.config["UPLOAD_FOLDER"]
            dest_dir = _Path(upload_folder) / str(user_id) / str(year) / "Charitable_Records"
            dest_dir.mkdir(parents=True, exist_ok=True)
            original_name = file.filename
            stored_name = f"{secrets.token_hex(4)}_{secure_filename(original_name)}"
            file.save(str(dest_dir / stored_name))
            save_upload(
                db_path=_portal_db(),
                user_id=user_id,
                tax_year=year,
                category="Charitable_Records",
                filename=stored_name,
                original_name=original_name,
            )
        else:
            flash("File type not allowed; entry was saved without the file.", "warning")

    return redirect(url_for("preparer.client_detail", user_id=user_id, year=year))


@preparer_bp.route("/client/<int:user_id>/manual-entry/<int:year>/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete_manual_entry_route(user_id: int, year: int, entry_id: int):
    delete_manual_entry(_preparer_db(), entry_id, user_id)
    flash("Entry deleted.", "success")
    return redirect(url_for("preparer.client_detail", user_id=user_id, year=year))


def _generate_1040_pdf(user_id: int, year: int) -> bytes:
    from portal.database import get_user_by_id
    from .form_1040_filler import aggregate_1040_data, fill_1040_pdf

    user        = get_user_by_id(_portal_db(), user_id)
    parsed_docs = get_parsed_documents(_preparer_db(), user_id, year)
    manual_entries = get_manual_entries(_preparer_db(), user_id, year)
    data        = aggregate_1040_data(parsed_docs, user or {}, year, manual_entries=manual_entries)
    data["_user"] = user or {}
    pdf_forms_dir = str(Path(current_app.root_path).parent / "pdf_forms")
    return fill_1040_pdf(data, pdf_forms_dir)


@preparer_bp.route("/client/<int:user_id>/tax-return/pdf")
@login_required
def tax_return_pdf(user_id: int):
    year = int(request.args.get("year", _tax_year_context()["current_year"]))
    pdf_bytes = _generate_1040_pdf(user_id, year)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=False,
    )


@preparer_bp.route("/client/<int:user_id>/tax-return/download")
@login_required
def tax_return_download(user_id: int):
    year = int(request.args.get("year", _tax_year_context()["current_year"]))
    pdf_bytes = _generate_1040_pdf(user_id, year)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"Form_1040_draft_{year}.pdf",
    )


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


