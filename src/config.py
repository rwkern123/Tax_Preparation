from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
MIN_TEXT_LENGTH_FOR_OCR_SKIP = 120


@dataclass(frozen=True)
class AppConfig:
    root: Path
    tax_year: int
    enable_ocr: bool = False
    redact: bool = False
    verbose: bool = False
    client_filter: str | None = None
    organize: bool = False
    organize_dry_run: bool = False
    taxpayer_name: str | None = None
    spouse_name: str | None = None
    spouse_aliases: tuple[str, ...] = ()
    compare_prior_year: bool = False
    prior_year_root: Path | None = None
