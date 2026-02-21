from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from src.classify import classify_document
from src.config import SUPPORTED_EXTENSIONS


@dataclass(frozen=True)
class OwnerContext:
    taxpayer_name: Optional[str] = None
    spouse_name: Optional[str] = None
    spouse_aliases: tuple[str, ...] = ()


def _normalize_token(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def detect_owner_from_name(file_name: str, context: OwnerContext) -> str:
    normalized = _normalize_token(file_name)

    def name_tokens(full_name: Optional[str]) -> list[str]:
        if not full_name:
            return []
        parts = [p for p in full_name.replace("_", " ").split() if p]
        return [_normalize_token(p) for p in parts] + [_normalize_token(full_name)]

    taxpayer_tokens = set(name_tokens(context.taxpayer_name))
    spouse_tokens = set(name_tokens(context.spouse_name))
    for alias in context.spouse_aliases:
        spouse_tokens.update(name_tokens(alias))

    has_taxpayer = any(token and token in normalized for token in taxpayer_tokens)
    has_spouse = any(token and token in normalized for token in spouse_tokens)

    if "joint" in normalized or (has_taxpayer and has_spouse):
        return "Joint"
    if has_taxpayer:
        return "Taxpayer"
    if has_spouse:
        return "Spouse"
    return "Unsorted"


def _iter_input_files(client_dir: Path) -> Iterable[Path]:
    skip_roots = {"_workpapers", "01_Taxpayer", "02_Spouse", "03_Joint", "04_Unsorted"}
    for path in client_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if any(part in skip_roots for part in path.parts):
            continue
        yield path


def _doc_bucket(doc_type: str) -> str:
    return {
        "w2": "W2",
        "brokerage_1099": "Brokerage_1099",
        "form_1098": "Form_1098",
    }.get(doc_type, "Other")


def _owner_bucket(owner: str) -> str:
    return {
        "Taxpayer": "01_Taxpayer",
        "Spouse": "02_Spouse",
        "Joint": "03_Joint",
    }.get(owner, "04_Unsorted")


def organize_client_documents(client_dir: Path, context: OwnerContext, dry_run: bool = False) -> list[dict[str, str]]:
    operations: list[dict[str, str]] = []
    for file_path in sorted(_iter_input_files(client_dir)):
        doc_type, _, _ = classify_document(file_path, "")
        owner = detect_owner_from_name(file_path.name, context)
        destination_dir = client_dir / _owner_bucket(owner) / _doc_bucket(doc_type)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / file_path.name

        if destination.exists() and destination.resolve() != file_path.resolve():
            stem, suffix = file_path.stem, file_path.suffix
            i = 1
            while True:
                candidate = destination_dir / f"{stem}_{i}{suffix}"
                if not candidate.exists():
                    destination = candidate
                    break
                i += 1

        operations.append({"source": str(file_path), "destination": str(destination), "doc_type": doc_type, "owner": owner})
        if not dry_run and destination.resolve() != file_path.resolve():
            shutil.move(str(file_path), str(destination))

    return operations
