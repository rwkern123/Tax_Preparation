from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, Iterable, List

from src.config import SUPPORTED_EXTENSIONS


def discover_clients(root: Path, client_filter: str | None = None) -> List[Path]:
    clients = [p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")]
    if client_filter:
        clients = [p for p in clients if p.name.lower() == client_filter.lower()]
    return sorted(clients)


def iter_supported_files(client_dir: Path) -> Iterable[Path]:
    for path in client_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS and "_workpapers" not in path.parts:
            yield path


def file_sha256(path: Path, chunk_size: int = 65536) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def index_client_files(client_dir: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for file_path in iter_supported_files(client_dir):
        rows.append(
            {
                "file_path": str(file_path),
                "file_name": file_path.name,
                "sha256": file_sha256(file_path),
            }
        )
    return rows
