import sqlite3
import json
from datetime import datetime


SCHEMA = """
CREATE TABLE IF NOT EXISTS parsed_documents (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_id        INTEGER NOT NULL UNIQUE,
    user_id          INTEGER NOT NULL,
    tax_year         INTEGER NOT NULL,
    category         TEXT NOT NULL,
    original_name    TEXT NOT NULL,
    file_path        TEXT NOT NULL,
    doc_type         TEXT NOT NULL DEFAULT 'unknown',
    confidence       REAL NOT NULL DEFAULT 0.0,
    parsing_status   TEXT NOT NULL DEFAULT 'pending',
    parse_error      TEXT,
    parsed_at        TEXT,
    extracted_json   TEXT NOT NULL DEFAULT '{}',
    drake_json       TEXT NOT NULL DEFAULT '{}',
    flags_json       TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_parsed_user_year ON parsed_documents(user_id, tax_year);
"""


def _get_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_preparer_db(db_path: str) -> None:
    conn = _get_db(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def upsert_parsed_document(
    db_path: str,
    upload_id: int,
    user_id: int,
    tax_year: int,
    category: str,
    original_name: str,
    file_path: str,
    doc_type: str,
    confidence: float,
    parsing_status: str,
    parse_error: str | None,
    extracted_json: dict,
    drake_json: dict,
    flags: list,
) -> None:
    parsed_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    conn = _get_db(db_path)
    try:
        conn.execute(
            """INSERT INTO parsed_documents
               (upload_id, user_id, tax_year, category, original_name, file_path,
                doc_type, confidence, parsing_status, parse_error, parsed_at,
                extracted_json, drake_json, flags_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(upload_id) DO UPDATE SET
                 doc_type=excluded.doc_type,
                 confidence=excluded.confidence,
                 parsing_status=excluded.parsing_status,
                 parse_error=excluded.parse_error,
                 parsed_at=excluded.parsed_at,
                 extracted_json=excluded.extracted_json,
                 drake_json=excluded.drake_json,
                 flags_json=excluded.flags_json""",
            (
                upload_id, user_id, tax_year, category, original_name, file_path,
                doc_type, confidence, parsing_status, parse_error, parsed_at,
                json.dumps(extracted_json), json.dumps(drake_json), json.dumps(flags),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_parsed_documents(db_path: str, user_id: int, tax_year: int) -> list[dict]:
    conn = _get_db(db_path)
    try:
        rows = conn.execute(
            """SELECT * FROM parsed_documents
               WHERE user_id = ? AND tax_year = ?
               ORDER BY category, original_name""",
            (user_id, tax_year),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["extracted_json"] = json.loads(d["extracted_json"])
            d["drake_json"] = json.loads(d["drake_json"])
            d["flags_json"] = json.loads(d["flags_json"])
            result.append(d)
        return result
    finally:
        conn.close()


def get_parsed_document_by_upload_id(db_path: str, upload_id: int) -> dict | None:
    conn = _get_db(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM parsed_documents WHERE upload_id = ?", (upload_id,)
        ).fetchone()
        if row:
            d = dict(row)
            d["extracted_json"] = json.loads(d["extracted_json"])
            d["drake_json"] = json.loads(d["drake_json"])
            d["flags_json"] = json.loads(d["flags_json"])
            return d
        return None
    finally:
        conn.close()


def reparse_document(db_path: str, upload_id: int, use_ocr: bool = False) -> None:
    """Re-trigger parsing for a single document by upload_id."""
    conn = _get_db(db_path)
    try:
        row = conn.execute(
            "SELECT file_path, user_id, tax_year, category, original_name FROM parsed_documents WHERE upload_id = ?",
            (upload_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return

    from .parser_bridge import parse_uploaded_file

    result = parse_uploaded_file(row["file_path"], use_ocr=use_ocr)
    upsert_parsed_document(
        db_path=db_path,
        upload_id=upload_id,
        user_id=row["user_id"],
        tax_year=row["tax_year"],
        category=row["category"],
        original_name=row["original_name"],
        file_path=row["file_path"],
        doc_type=result["doc_type"],
        confidence=result["confidence"],
        parsing_status=result["parsing_status"],
        parse_error=result["parse_error"],
        extracted_json=result["extracted"],
        drake_json=result["drake"],
        flags=result["flags"],
    )


def reparse_document_azure(
    db_path: str,
    upload_id: int,
    endpoint: str,
    api_key: str,
) -> None:
    """Re-parse a document using Azure Document Intelligence."""
    conn = _get_db(db_path)
    try:
        row = conn.execute(
            "SELECT file_path, user_id, tax_year, category, original_name, doc_type "
            "FROM parsed_documents WHERE upload_id = ?",
            (upload_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return

    from .parser_bridge import azure_parse_uploaded_file

    result = azure_parse_uploaded_file(
        row["file_path"],
        endpoint=endpoint,
        api_key=api_key,
        doc_type_hint=row["doc_type"],
    )
    upsert_parsed_document(
        db_path=db_path,
        upload_id=upload_id,
        user_id=row["user_id"],
        tax_year=row["tax_year"],
        category=row["category"],
        original_name=row["original_name"],
        file_path=row["file_path"],
        doc_type=result["doc_type"],
        confidence=result["confidence"],
        parsing_status=result["parsing_status"],
        parse_error=result["parse_error"],
        extracted_json=result["extracted"],
        drake_json=result["drake"],
        flags=result["flags"],
    )


def delete_parsed_document(db_path: str, upload_id: int) -> dict | None:
    """Delete a parsed_documents record by upload_id. Returns the deleted row or None."""
    conn = _get_db(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM parsed_documents WHERE upload_id = ?", (upload_id,)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM parsed_documents WHERE upload_id = ?", (upload_id,))
            conn.commit()
            d = dict(row)
            d["extracted_json"] = json.loads(d["extracted_json"])
            d["drake_json"] = json.loads(d["drake_json"])
            d["flags_json"] = json.loads(d["flags_json"])
            return d
        return None
    finally:
        conn.close()


def get_preparer_client_list(
    portal_db: str, preparer_db: str, tax_year: int
) -> list[dict]:
    """
    Join portal.db users/uploads with preparer.db parse results.
    Returns one dict per user with status badge info.
    """
    conn = _get_db(preparer_db)
    # Use parameterised ATTACH — SQLite doesn't support ? in ATTACH, so
    # we use a safe string format (portal_db is a local file path, not user input).
    conn.execute(f"ATTACH DATABASE '{portal_db}' AS portal")
    try:
        rows = conn.execute(
            """
            SELECT
                u.id                                        AS user_id,
                u.first_name || ' ' || u.last_name          AS display_name,
                u.filing_status,
                COALESCE(qr.completed, 0)                   AS questionnaire_completed,
                COALESCE(up_counts.total_uploads, 0)        AS doc_count,
                COALESCE(pd_counts.parsed_count, 0)         AS parsed_count,
                COALESCE(pd_counts.pending_count, 0)        AS pending_count,
                COALESCE(pd_counts.error_doc_count, 0)      AS error_doc_count,
                COALESCE(pd_counts.flag_count, 0)           AS flag_count,
                COALESCE(pd_counts.error_flag_count, 0)     AS error_flag_count
            FROM portal.users u
            LEFT JOIN portal.questionnaire_responses qr
                ON qr.user_id = u.id AND qr.tax_year = ?
            LEFT JOIN (
                SELECT user_id, COUNT(*) AS total_uploads
                FROM portal.uploads WHERE tax_year = ?
                GROUP BY user_id
            ) up_counts ON up_counts.user_id = u.id
            LEFT JOIN (
                SELECT
                    user_id,
                    COUNT(*) FILTER (WHERE parsing_status = 'done')    AS parsed_count,
                    COUNT(*) FILTER (WHERE parsing_status = 'pending') AS pending_count,
                    COUNT(*) FILTER (WHERE parsing_status = 'failed')  AS error_doc_count,
                    SUM(json_array_length(flags_json))                 AS flag_count,
                    SUM(
                        (SELECT COUNT(*) FROM json_each(flags_json) AS f
                         WHERE json_extract(f.value, '$.severity') = 'error')
                    )                                                  AS error_flag_count
                FROM parsed_documents
                WHERE tax_year = ?
                GROUP BY user_id
            ) pd_counts ON pd_counts.user_id = u.id
            ORDER BY u.last_name, u.first_name
            """,
            (tax_year, tax_year, tax_year),
        ).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            if d["error_flag_count"] and d["error_flag_count"] > 0:
                d["status"] = "needs_attention"
                d["status_class"] = "danger"
            elif not d["questionnaire_completed"] or (d["flag_count"] and d["flag_count"] > 0):
                d["status"] = "in_progress"
                d["status_class"] = "warning"
            else:
                d["status"] = "complete"
                d["status_class"] = "success"
            result.append(d)
        return result
    finally:
        conn.close()
