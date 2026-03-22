"""
Import clients from an existing TaxClients folder structure into portal.db.

Expected folder naming convention:
  LastName_FirstName_SpouseName_FilingStatus
  LastName_FirstName_FilingStatus
  LastName_FirstName           (filing status defaults to 'single')

Examples:
  Kern_Ryan_Brittany_MFJ  -> Ryan Kern / Brittany Kern, MFJ
  Smith_John_Single       -> John Smith, single
  Jones_Mary              -> Mary Jones, single
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

FILING_CODES = {"MFJ", "MFS", "HOH", "QW", "SINGLE"}
FILING_MAP = {
    "MFJ": "mfj",
    "MFS": "mfs",
    "HOH": "hoh",
    "QW": "qw",
    "SINGLE": "single",
}


def _parse_folder_name(name: str) -> dict | None:
    """
    Parse a client folder name into components.
    Returns dict with keys: last_name, first_name, spouse_first_name, filing_status
    Returns None if the folder should be skipped (e.g. starts with _ or .).
    """
    if name.startswith(("_", ".")):
        return None

    parts = name.split("_")
    if len(parts) < 2:
        return None

    last_name = parts[0]
    first_name = parts[1]

    # Check if last token is a filing status code
    last_token = parts[-1].upper()
    if last_token in FILING_CODES and len(parts) >= 3:
        filing_status = FILING_MAP[last_token]
        middle_parts = parts[2:-1]
    else:
        filing_status = "single"
        middle_parts = parts[2:]

    spouse_first_name = middle_parts[0] if middle_parts else None

    return {
        "last_name": last_name,
        "first_name": first_name,
        "spouse_first_name": spouse_first_name,
        "filing_status": filing_status,
        "folder_name": name,
    }


def import_clients_from_folder(root_folder: str, portal_db_path: str) -> dict:
    """
    Scan root_folder for client subdirectories and insert any new clients
    into portal.db.

    Returns:
        {"imported": int, "skipped": int, "errors": list[str]}
    """
    root = Path(root_folder)
    if not root.exists() or not root.is_dir():
        return {"imported": 0, "skipped": 0, "errors": [f"Folder not found: {root_folder}"]}

    conn = sqlite3.connect(portal_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    imported = 0
    skipped = 0
    errors: list[str] = []

    try:
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue

            parsed = _parse_folder_name(entry.name)
            if parsed is None:
                continue

            # Build a placeholder email unique to this client
            placeholder_email = (
                f"{parsed['first_name'].lower()}.{parsed['last_name'].lower()}"
                f"@imported.local"
            )

            # If the same first+last name already has an entry, make email unique
            existing = conn.execute(
                "SELECT id FROM users WHERE email = ?", (placeholder_email,)
            ).fetchone()
            if existing:
                skipped += 1
                continue

            # Also check by first+last name match (avoid duplicates with different emails)
            name_match = conn.execute(
                "SELECT id FROM users WHERE first_name = ? AND last_name = ?",
                (parsed["first_name"], parsed["last_name"]),
            ).fetchone()
            if name_match:
                skipped += 1
                continue

            try:
                cursor = conn.execute(
                    """INSERT INTO users
                       (email, phone, password_hash, first_name, last_name,
                        dob, ssn, address, city, state, zip, filing_status, two_fa_method)
                       VALUES (?, '', 'imported', ?, ?, '', '', '', '', '', ?, ?, 'email')""",
                    (
                        placeholder_email,
                        parsed["first_name"],
                        parsed["last_name"],
                        parsed["folder_name"],  # stored in zip field as source reference
                        parsed["filing_status"],
                    ),
                )
                user_id = cursor.lastrowid

                # Add spouse record if present and filing status suggests one
                if parsed["spouse_first_name"] and parsed["filing_status"] in ("mfj", "mfs"):
                    conn.execute(
                        """INSERT INTO spouses (user_id, first_name, last_name, dob, ssn)
                           VALUES (?, ?, ?, '', '')""",
                        (user_id, parsed["spouse_first_name"], parsed["last_name"]),
                    )

                conn.commit()
                imported += 1

            except sqlite3.IntegrityError as exc:
                skipped += 1
            except Exception as exc:
                errors.append(f"{entry.name}: {exc}")

    finally:
        conn.close()

    return {"imported": imported, "skipped": skipped, "errors": errors}
