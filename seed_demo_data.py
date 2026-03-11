#!/usr/bin/env python3
"""
Seed demo clients and parsed documents so the preparer dashboard has data to display.
Run once: python seed_demo_data.py

Safe to re-run — skips users that already exist by email.
"""
import sqlite3, json, hashlib
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
PORTAL_DB   = ROOT / "portal_data" / "portal.db"
PREPARER_DB = ROOT / "portal_data" / "preparer.db"

TAX_YEAR = 2024

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _portal(sql, params=()):
    conn = sqlite3.connect(PORTAL_DB)
    conn.row_factory = sqlite3.Row
    try:
        r = conn.execute(sql, params)
        conn.commit()
        return r
    finally:
        conn.close()

def _preparer(sql, params=()):
    conn = sqlite3.connect(PREPARER_DB)
    conn.row_factory = sqlite3.Row
    try:
        r = conn.execute(sql, params)
        conn.commit()
        return r
    finally:
        conn.close()

def _get_portal(sql, params=()):
    conn = sqlite3.connect(PORTAL_DB)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()

def _pw_hash(pw: str) -> str:
    # Werkzeug pbkdf2 — use plain sha256 for demo (portal auth will reject, dashboard only)
    return "pbkdf2:sha256:600000$demo$" + hashlib.sha256(pw.encode()).hexdigest()

def _upsert_user(email, first, last, filing_status, dob="1980-01-01", ssn="000-00-0000") -> int:
    row = sqlite3.connect(PORTAL_DB).execute(
        "SELECT id FROM users WHERE email=?", (email,)
    ).fetchone()
    if row:
        print(f"  User {email} already exists (id={row[0]}), skipping insert.")
        return row[0]
    r = _portal(
        """INSERT INTO users
           (email, phone, password_hash, first_name, last_name, dob, ssn,
            address, city, state, zip, filing_status, two_fa_method)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (email, "555-000-0000", _pw_hash("demo"), first, last, dob, ssn,
         "123 Main St", "Houston", "TX", "77019", filing_status, "email"),
    )
    # Re-fetch id after commit
    uid = sqlite3.connect(PORTAL_DB).execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]
    print(f"  Created user {first} {last} (id={uid})")
    return uid

def _upsert_upload(user_id, tax_year, category, original_name) -> int:
    row = sqlite3.connect(PORTAL_DB).execute(
        "SELECT id FROM uploads WHERE user_id=? AND tax_year=? AND original_name=?",
        (user_id, tax_year, original_name)
    ).fetchone()
    if row:
        return row[0]
    _portal(
        "INSERT INTO uploads (user_id, tax_year, category, filename, original_name) VALUES (?,?,?,?,?)",
        (user_id, tax_year, category, original_name, original_name),
    )
    return sqlite3.connect(PORTAL_DB).execute(
        "SELECT id FROM uploads WHERE user_id=? AND tax_year=? AND original_name=?",
        (user_id, tax_year, original_name)
    ).fetchone()[0]

def _upsert_parsed(upload_id, user_id, tax_year, category, original_name,
                   doc_type, confidence, parsing_status, parse_error,
                   extracted, drake, flags):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    _preparer(
        """INSERT INTO parsed_documents
           (upload_id, user_id, tax_year, category, original_name, file_path,
            doc_type, confidence, parsing_status, parse_error, parsed_at,
            extracted_json, drake_json, flags_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(upload_id) DO UPDATE SET
             doc_type=excluded.doc_type,
             confidence=excluded.confidence,
             parsing_status=excluded.parsing_status,
             parse_error=excluded.parse_error,
             parsed_at=excluded.parsed_at,
             extracted_json=excluded.extracted_json,
             drake_json=excluded.drake_json,
             flags_json=excluded.flags_json""",
        (upload_id, user_id, tax_year, category, original_name, "",
         doc_type, confidence, parsing_status, parse_error, now,
         json.dumps(extracted), json.dumps(drake), json.dumps(flags)),
    )

def _save_questionnaire(user_id, answers, completed=True):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    _portal(
        """INSERT INTO questionnaire_responses
           (user_id, tax_year, answers, completed, updated_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT(user_id, tax_year) DO UPDATE SET
             answers=excluded.answers,
             completed=excluded.completed,
             updated_at=excluded.updated_at""",
        (user_id, TAX_YEAR, json.dumps(answers), 1 if completed else 0, now),
    )

# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

CLIENTS = [

    # ── Client 1: Clean, complete, no flags ──────────────────────────────
    {
        "email": "johnson.mark@demo.test",
        "first": "Mark",  "last": "Johnson",
        "filing_status": "married_filing_jointly",
        "questionnaire": {
            "has_w2_tp": "yes", "has_w2_sp": "yes",
            "has_mortgage": "yes", "has_brokerage": "no",
            "has_dependents": "no",
        },
        "questionnaire_complete": True,
        "documents": [
            {
                "category": "w2_tp",
                "name": "Mark_W2_Acme_Corp_2024.pdf",
                "doc_type": "w2",
                "confidence": 0.92,
                "status": "done",
                "extracted": {"w2": [{
                    "employer_name": "Acme Corporation",
                    "employer_ein": "12-3456789",
                    "employee_name": "Mark Johnson",
                    "box1_wages": 95000.00,
                    "box2_fed_withholding": 14200.00,
                    "box3_ss_wages": 95000.00,
                    "box4_ss_tax": 5890.00,
                    "box5_medicare_wages": 95000.00,
                    "box6_medicare_tax": 1377.50,
                    "box12": {"D": 2000.00},
                    "box13_retirement_plan": True,
                    "box16_state_wages": 95000.00,
                    "box17_state_tax": 4750.00,
                    "employer_address": "500 Commerce St",
                    "employer_city": "Houston",
                    "employer_state": "TX",
                    "employer_zip": "77002",
                    "confidence": 0.92,
                }]},
                "drake": {
                    "w2_employer_name": "Acme Corporation",
                    "w2_employer_ein": "12-3456789",
                    "w2_box1_wages": 95000.00,
                    "w2_box2_federal_withheld": 14200.00,
                },
                "flags": [],
            },
            {
                "category": "w2_sp",
                "name": "Sarah_W2_TechCo_2024.pdf",
                "doc_type": "w2",
                "confidence": 0.88,
                "status": "done",
                "extracted": {"w2": [{
                    "employer_name": "TechCo Solutions LLC",
                    "employer_ein": "98-7654321",
                    "employee_name": "Sarah Johnson",
                    "box1_wages": 72000.00,
                    "box2_fed_withholding": 10200.00,
                    "box3_ss_wages": 72000.00,
                    "box4_ss_tax": 4464.00,
                    "box5_medicare_wages": 72000.00,
                    "box6_medicare_tax": 1044.00,
                    "box12": {},
                    "box13_retirement_plan": False,
                    "box16_state_wages": 72000.00,
                    "box17_state_tax": 3600.00,
                    "confidence": 0.88,
                }]},
                "drake": {"w2_box1_wages": 72000.00},
                "flags": [],
            },
            {
                "category": "mortgage",
                "name": "Chase_1098_2024.pdf",
                "doc_type": "form_1098",
                "confidence": 0.95,
                "status": "done",
                "extracted": {"form_1098": [{
                    "lender_name": "Chase Bank Mortgage",
                    "payer_name": "Mark Johnson",
                    "borrower_names": ["Mark Johnson", "Sarah Johnson"],
                    "mortgage_interest_received": 18450.00,
                    "points_paid": None,
                    "mortgage_insurance_premiums": 1200.00,
                    "real_estate_taxes": 6800.00,
                    "mortgage_principal_outstanding": 385000.00,
                    "confidence": 0.95,
                }]},
                "drake": {
                    "f1098_lender_name": "Chase Bank Mortgage",
                    "f1098_mortgage_interest": 18450.00,
                    "f1098_real_estate_taxes": 6800.00,
                },
                "flags": [],
            },
        ],
    },

    # ── Client 2: Needs attention — low confidence W-2, missing fields ───
    {
        "email": "rodriguez.elena@demo.test",
        "first": "Elena", "last": "Rodriguez",
        "filing_status": "single",
        "questionnaire": {
            "has_w2_tp": "yes", "has_mortgage": "no",
            "has_brokerage": "yes",
        },
        "questionnaire_complete": True,
        "documents": [
            {
                "category": "w2_tp",
                "name": "W2_2024_scan.pdf",
                "doc_type": "w2",
                "confidence": 0.28,
                "status": "done",
                "extracted": {"w2": [{
                    "employer_name": None,
                    "employer_ein": None,
                    "employee_name": "Elena Rodriguez",
                    "box1_wages": 58000.00,
                    "box2_fed_withholding": None,
                    "box3_ss_wages": None,
                    "box4_ss_tax": None,
                    "box5_medicare_wages": None,
                    "box6_medicare_tax": None,
                    "box12": {},
                    "box13_retirement_plan": False,
                    "box16_state_wages": None,
                    "box17_state_tax": None,
                    "confidence": 0.28,
                }]},
                "drake": {"w2_box1_wages": 58000.00},
                "flags": [
                    {"type": "low_confidence", "severity": "error",
                     "message": "Very low extraction confidence (28%). Manual review required.",
                     "field": "confidence"},
                    {"type": "missing_field", "severity": "warning",
                     "message": "Could not extract 'Employer Name'. Verify manually.",
                     "field": "employer_name"},
                    {"type": "missing_field", "severity": "warning",
                     "message": "Could not extract 'Employer EIN'. Verify manually.",
                     "field": "employer_ein"},
                    {"type": "missing_field", "severity": "warning",
                     "message": "Could not extract 'Box 2 Federal Withheld'. Verify manually.",
                     "field": "box2_fed_withholding"},
                ],
            },
            {
                "category": "brokerage",
                "name": "Fidelity_1099_2024.pdf",
                "doc_type": "brokerage_1099",
                "confidence": 0.81,
                "status": "done",
                "extracted": {
                    "brokerage_1099": [{
                        "broker_name": "Fidelity Investments",
                        "div_ordinary": 3240.50,
                        "div_qualified": 2100.00,
                        "div_cap_gain_distributions": 450.00,
                        "div_foreign_tax_paid": 87.20,
                        "int_interest_income": 1120.00,
                        "int_us_treasury": 640.00,
                        "b_summary": {
                            "proceeds": 42500.00,
                            "cost_basis": 38200.00,
                            "wash_sales": 350.00,
                            "short_term_gain_loss": 1800.00,
                            "long_term_gain_loss": 2500.00,
                        },
                        "confidence": 0.81,
                    }],
                    "brokerage_1099_trades": [
                        {
                            "description": "Apple Inc (AAPL)",
                            "security_identifier": "AAPL",
                            "date_acquired": "2023-03-15",
                            "date_sold_or_disposed": "2024-08-20",
                            "proceeds_gross": 15200.00,
                            "cost_basis": 12800.00,
                            "realized_gain_loss": 2400.00,
                            "holding_period": "long",
                            "basis_reported_to_irs": "covered",
                            "form_8949_box": "D",
                            "wash_sale_code": None,
                            "wash_sale_amount": None,
                        },
                        {
                            "description": "Microsoft Corp (MSFT)",
                            "security_identifier": "MSFT",
                            "date_acquired": "2024-05-01",
                            "date_sold_or_disposed": "2024-09-10",
                            "proceeds_gross": 8700.00,
                            "cost_basis": 9100.00,
                            "realized_gain_loss": -400.00,
                            "holding_period": "short",
                            "basis_reported_to_irs": "covered",
                            "form_8949_box": "A",
                            "wash_sale_code": "W",
                            "wash_sale_amount": 350.00,
                        },
                        {
                            "description": "Vanguard S&P 500 ETF (VOO)",
                            "security_identifier": "VOO",
                            "date_acquired": "2022-11-15",
                            "date_sold_or_disposed": "2024-07-30",
                            "proceeds_gross": 18600.00,
                            "cost_basis": 16300.00,
                            "realized_gain_loss": 2300.00,
                            "holding_period": "long",
                            "basis_reported_to_irs": "covered",
                            "form_8949_box": "D",
                            "wash_sale_code": None,
                            "wash_sale_amount": None,
                        },
                    ],
                },
                "drake": {
                    "b1099_broker_name": "Fidelity Investments",
                    "b1099_ordinary_dividends": 3240.50,
                    "b1099_qualified_dividends": 2100.00,
                    "b1099_proceeds": 42500.00,
                    "b1099_cost_basis": 38200.00,
                },
                "flags": [],
            },
        ],
    },

    # ── Client 3: In progress — questionnaire incomplete, 1 doc uploaded ─
    {
        "email": "patel.raj@demo.test",
        "first": "Raj", "last": "Patel",
        "filing_status": "married_filing_jointly",
        "questionnaire": {
            "has_w2_tp": "yes",
        },
        "questionnaire_complete": False,
        "documents": [
            {
                "category": "w2_tp",
                "name": "Raj_W2_NovaTech_2024.pdf",
                "doc_type": "w2",
                "confidence": 0.76,
                "status": "done",
                "extracted": {"w2": [{
                    "employer_name": "NovaTech Industries",
                    "employer_ein": "45-6789012",
                    "employee_name": "Raj Patel",
                    "box1_wages": 135000.00,
                    "box2_fed_withholding": 24500.00,
                    "box3_ss_wages": 160200.00,
                    "box4_ss_tax": 9932.40,
                    "box5_medicare_wages": 135000.00,
                    "box6_medicare_tax": 1957.50,
                    "box12": {"D": 19500.00, "AA": 5000.00},
                    "box13_retirement_plan": True,
                    "box16_state_wages": 135000.00,
                    "box17_state_tax": 6750.00,
                    "confidence": 0.76,
                }]},
                "drake": {
                    "w2_employer_name": "NovaTech Industries",
                    "w2_box1_wages": 135000.00,
                    "w2_box2_federal_withheld": 24500.00,
                },
                "flags": [
                    {"type": "low_confidence", "severity": "warning",
                     "message": "Low extraction confidence (76%). Verify extracted fields.",
                     "field": "confidence"},
                ],
            },
        ],
    },

    # ── Client 4: Failed parse on one doc, unclassified doc ──────────────
    {
        "email": "chen.wei@demo.test",
        "first": "Wei", "last": "Chen",
        "filing_status": "single",
        "questionnaire": {
            "has_w2_tp": "yes", "has_brokerage": "no", "has_mortgage": "no",
        },
        "questionnaire_complete": True,
        "documents": [
            {
                "category": "w2_tp",
                "name": "W2_employer_2024.pdf",
                "doc_type": "w2",
                "confidence": 0.89,
                "status": "done",
                "extracted": {"w2": [{
                    "employer_name": "Global Consulting Group",
                    "employer_ein": "77-1234567",
                    "employee_name": "Wei Chen",
                    "box1_wages": 88500.00,
                    "box2_fed_withholding": 13800.00,
                    "box3_ss_wages": 88500.00,
                    "box4_ss_tax": 5487.00,
                    "box5_medicare_wages": 88500.00,
                    "box6_medicare_tax": 1283.25,
                    "box12": {},
                    "box13_retirement_plan": False,
                    "box16_state_wages": 88500.00,
                    "box17_state_tax": 4425.00,
                    "confidence": 0.89,
                }]},
                "drake": {"w2_box1_wages": 88500.00},
                "flags": [],
            },
            {
                "category": "other",
                "name": "unknown_document.pdf",
                "doc_type": "unknown",
                "confidence": 0.0,
                "status": "done",
                "extracted": {},
                "drake": {},
                "flags": [
                    {"type": "unclassified", "severity": "warning",
                     "message": "Document could not be classified. Review manually.",
                     "field": None},
                ],
            },
            {
                "category": "other",
                "name": "corrupted_scan.pdf",
                "doc_type": "unknown",
                "confidence": 0.0,
                "status": "failed",
                "extracted": {},
                "drake": {},
                "flags": [
                    {"type": "parse_error", "severity": "error",
                     "message": "Parsing failed: PDF appears to be corrupted or password-protected.",
                     "field": None},
                ],
                "parse_error": "PDF appears to be corrupted or password-protected.",
            },
        ],
    },
]

# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

def seed():
    # Make sure DBs are initialised
    from portal.app import create_app
    create_app()  # triggers init_db and init_preparer_db

    print("\nSeeding demo clients...\n")
    for client in CLIENTS:
        print(f"Client: {client['first']} {client['last']} ({client['filing_status']})")
        uid = _upsert_user(
            email=client["email"],
            first=client["first"],
            last=client["last"],
            filing_status=client["filing_status"],
        )
        _save_questionnaire(uid, client["questionnaire"], completed=client["questionnaire_complete"])

        for doc in client["documents"]:
            up_id = _upsert_upload(uid, TAX_YEAR, doc["category"], doc["name"])
            _upsert_parsed(
                upload_id=up_id,
                user_id=uid,
                tax_year=TAX_YEAR,
                category=doc["category"],
                original_name=doc["name"],
                doc_type=doc["doc_type"],
                confidence=doc["confidence"],
                parsing_status=doc["status"],
                parse_error=doc.get("parse_error"),
                extracted=doc["extracted"],
                drake=doc["drake"],
                flags=doc["flags"],
            )
            status_icon = "OK" if doc["status"] == "done" else "XX"
            print(f"  {status_icon} {doc['name']} ({doc['doc_type']}, conf={doc['confidence']:.0%})")

    print("\nDone. Open http://127.0.0.1:8800 and log in with 'changeme'.\n")


if __name__ == "__main__":
    seed()
