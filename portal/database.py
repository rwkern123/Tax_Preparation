import sqlite3
import json
from datetime import datetime, timedelta
from contextlib import contextmanager


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    phone TEXT,
    password_hash TEXT NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    dob TEXT NOT NULL,
    ssn TEXT NOT NULL,
    address TEXT,
    city TEXT,
    state TEXT,
    zip TEXT,
    filing_status TEXT NOT NULL DEFAULT 'single',
    two_fa_method TEXT NOT NULL DEFAULT 'email',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS spouses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    dob TEXT NOT NULL,
    ssn TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS two_factor_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    method TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS questionnaire_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    tax_year INTEGER NOT NULL,
    answers TEXT NOT NULL DEFAULT '{}',
    completed INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, tax_year),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    tax_year INTEGER NOT NULL,
    category TEXT NOT NULL,
    filename TEXT NOT NULL,
    original_name TEXT NOT NULL,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
"""


def get_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str) -> None:
    conn = get_db(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def get_user_by_email(db_path: str, email: str) -> dict | None:
    conn = get_db(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(db_path: str, user_id: int) -> dict | None:
    conn = get_db(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_user(db_path: str, email: str, phone: str, password_hash: str,
                first_name: str, last_name: str, dob: str, ssn: str,
                address: str, city: str, state: str, zip_code: str,
                filing_status: str, two_fa_method: str) -> int:
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO users
               (email, phone, password_hash, first_name, last_name, dob, ssn,
                address, city, state, zip, filing_status, two_fa_method)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (email.lower().strip(), phone, password_hash, first_name, last_name,
             dob, ssn, address, city, state, zip_code, filing_status, two_fa_method)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def create_spouse(db_path: str, user_id: int, first_name: str, last_name: str,
                  dob: str, ssn: str) -> int:
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO spouses (user_id, first_name, last_name, dob, ssn)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 first_name=excluded.first_name,
                 last_name=excluded.last_name,
                 dob=excluded.dob,
                 ssn=excluded.ssn""",
            (user_id, first_name, last_name, dob, ssn)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_spouse(db_path: str, user_id: int) -> dict | None:
    conn = get_db(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM spouses WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def save_code(db_path: str, user_id: int, code: str, method: str) -> None:
    expires_at = (datetime.utcnow() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db(db_path)
    try:
        # Invalidate any prior unused codes for this user
        conn.execute(
            "UPDATE two_factor_codes SET used = 1 WHERE user_id = ? AND used = 0",
            (user_id,)
        )
        conn.execute(
            """INSERT INTO two_factor_codes (user_id, code, method, expires_at)
               VALUES (?, ?, ?, ?)""",
            (user_id, code, method, expires_at)
        )
        conn.commit()
    finally:
        conn.close()


def verify_code(db_path: str, user_id: int, code: str) -> bool:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db(db_path)
    try:
        row = conn.execute(
            """SELECT id FROM two_factor_codes
               WHERE user_id = ? AND code = ? AND used = 0 AND expires_at > ?
               ORDER BY id DESC LIMIT 1""",
            (user_id, code, now)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE two_factor_codes SET used = 1 WHERE id = ?", (row["id"],)
            )
            conn.commit()
            return True
        return False
    finally:
        conn.close()


def get_questionnaire(db_path: str, user_id: int, tax_year: int) -> dict | None:
    conn = get_db(db_path)
    try:
        row = conn.execute(
            """SELECT * FROM questionnaire_responses
               WHERE user_id = ? AND tax_year = ?""",
            (user_id, tax_year)
        ).fetchone()
        if row:
            result = dict(row)
            result["answers"] = json.loads(result["answers"])
            return result
        return None
    finally:
        conn.close()


def save_questionnaire(db_path: str, user_id: int, tax_year: int,
                       answers: dict, completed: bool = False) -> None:
    updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db(db_path)
    try:
        conn.execute(
            """INSERT INTO questionnaire_responses
               (user_id, tax_year, answers, completed, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id, tax_year) DO UPDATE SET
                 answers=excluded.answers,
                 completed=excluded.completed,
                 updated_at=excluded.updated_at""",
            (user_id, tax_year, json.dumps(answers), 1 if completed else 0, updated_at)
        )
        conn.commit()
    finally:
        conn.close()


def get_uploads(db_path: str, user_id: int, tax_year: int) -> list[dict]:
    conn = get_db(db_path)
    try:
        rows = conn.execute(
            """SELECT * FROM uploads WHERE user_id = ? AND tax_year = ?
               ORDER BY category, uploaded_at""",
            (user_id, tax_year)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_upload(db_path: str, user_id: int, tax_year: int, category: str,
                filename: str, original_name: str) -> int:
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            """INSERT INTO uploads
               (user_id, tax_year, category, filename, original_name)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, tax_year, category, filename, original_name)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def delete_upload(db_path: str, upload_id: int, user_id: int) -> dict | None:
    conn = get_db(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM uploads WHERE id = ? AND user_id = ?",
            (upload_id, user_id)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM uploads WHERE id = ?", (upload_id,))
            conn.commit()
            return dict(row)
        return None
    finally:
        conn.close()
