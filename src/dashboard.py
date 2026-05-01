from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Module-level mtime cache: key=(str_path, mtime) -> parsed result
_file_cache: dict[tuple, Any] = {}


def _read_cached(path: Path, loader):
    """Return loader(path) cached by (absolute_path, mtime). Returns None if file missing."""
    if not path.exists():
        return None
    key = (str(path.resolve()), path.stat().st_mtime)
    if key not in _file_cache:
        _file_cache[key] = loader(path)
    return _file_cache[key]


@dataclass
class ClientSummary:
    client: str
    workpapers_dir: Path
    has_outputs: bool
    document_count: int = 0
    unknown_count: int = 0
    error_count: int = 0
    task_count: int = 0
    tasks: list[str] = field(default_factory=list)
    extraction_counts: dict[str, int] = field(default_factory=dict)


def _parse_questions(path: Path) -> list[str]:
    tasks: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("- "):
            tasks.append(line[2:].strip())
    return tasks


def parse_questions_markdown(path: Path) -> list[str]:
    result = _read_cached(path, _parse_questions)
    return result if result is not None else []


def _parse_index(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return {
        "document_count": len(rows),
        "unknown_count": sum(1 for r in rows if r.get("doc_type") == "unknown"),
        "error_count": sum(1 for r in rows if r.get("doc_type") == "error"),
    }


def load_document_index(path: Path) -> dict[str, Any]:
    result = _read_cached(path, _parse_index)
    return result if result is not None else {"document_count": 0, "unknown_count": 0, "error_count": 0}


def _parse_extract_counts(path: Path) -> dict[str, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for key in ["w2", "brokerage_1099", "form_1098", "unknown"]:
        val = data.get(key)
        if isinstance(val, list):
            counts[key] = len(val)
    return counts


def load_extract_counts(path: Path) -> dict[str, int]:
    result = _read_cached(path, _parse_extract_counts)
    return result if result is not None else {}


def _parse_document_records(path: Path) -> list[dict[str, Any]]:
    """Load Document_Index.csv with key_fields column parsed from JSON string to dict."""
    records = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                row["key_fields"] = json.loads(row.get("key_fields") or "{}")
            except (json.JSONDecodeError, TypeError):
                row["key_fields"] = {}
            records.append(dict(row))
    return records


def load_document_records(path: Path) -> list[dict[str, Any]]:
    """Return per-document rows from Document_Index.csv with key_fields as parsed dicts."""
    result = _read_cached(path, _parse_document_records)
    return result if result is not None else []


def build_client_summary(client_dir: Path) -> ClientSummary:
    out_dir = client_dir / "_workpapers"
    has_outputs = out_dir.exists()
    summary = ClientSummary(client=client_dir.name, workpapers_dir=out_dir, has_outputs=has_outputs)
    if not has_outputs:
        return summary

    index_info = load_document_index(out_dir / "Document_Index.csv")
    summary.document_count = int(index_info["document_count"])
    summary.unknown_count = int(index_info["unknown_count"])
    summary.error_count = int(index_info["error_count"])
    summary.tasks = parse_questions_markdown(out_dir / "Questions_For_Client.md")
    summary.task_count = len(summary.tasks)
    summary.extraction_counts = load_extract_counts(out_dir / "Data_Extract.json")
    return summary


def list_client_summaries(root: Path) -> list[ClientSummary]:
    clients = [p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")]
    return sorted((build_client_summary(c) for c in clients), key=lambda x: x.client.lower())
