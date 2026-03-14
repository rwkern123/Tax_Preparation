"""
Persistent configuration for the Tax Preparer Dashboard.

Settings are stored in app_config.json at the project root.
This file is excluded from version control (.gitignore) because
it contains sensitive values like the Azure API key.
"""
from __future__ import annotations

import json
from pathlib import Path

# Always resolve relative to project root (one level above this file)
_CONFIG_PATH = Path(__file__).parent.parent / "app_config.json"

_DEFAULTS: dict = {
    "tax_year": 2024,
    "root_folder": "",
    "azure_endpoint": "",
    "azure_api_key": "",
    "azure_enabled": False,
}


def load() -> dict:
    """Return current config, merged with defaults for any missing keys."""
    if _CONFIG_PATH.exists():
        try:
            saved = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            saved = {}
    else:
        saved = {}
    return {**_DEFAULTS, **saved}


def save(updates: dict) -> None:
    """Merge updates into the existing config and write to disk."""
    current = load()
    current.update(updates)
    _CONFIG_PATH.write_text(
        json.dumps(current, indent=2), encoding="utf-8"
    )


def get(key: str, default=None):
    """Convenience: read a single key."""
    return load().get(key, default)
