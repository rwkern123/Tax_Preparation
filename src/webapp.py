from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

from src.dashboard import build_client_summary, list_client_summaries, load_document_records

# Fields from parsed dataclasses that are internal/structural and should not be shown as override inputs
_SKIP_FIELDS = frozenset({
    "confidence", "extraction_source", "trade_count", "trade_candidates",
    "b_summary", "box12", "borrower_names",
})


def _load_overrides(wp_dir: Path) -> dict:
    p = wp_dir / "overrides.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_overrides(wp_dir: Path, data: dict) -> None:
    (wp_dir / "overrides.json").write_text(
        json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
    )


def _prepare_records(records: list[dict], overrides: dict) -> list[dict]:
    """Flatten each document record into a display-ready dict for the template."""
    out = []
    for rec in records:
        sha = rec.get("sha256", "")
        doc_overrides = overrides.get(sha, {})
        field_overrides = doc_overrides.get("fields", {})

        scalar_fields = []
        for fname, val in rec.get("key_fields", {}).items():
            if fname in _SKIP_FIELDS:
                continue
            if isinstance(val, (dict, list)):
                continue
            scalar_fields.append({
                "name": fname,
                "original": val,
                "override": field_overrides.get(fname),
                "is_numeric": isinstance(val, (int, float)),
            })

        out.append({
            "sha256": sha,
            "sha_short": sha[:8] if sha else "",
            "file_name": rec.get("file_name", ""),
            "doc_type": rec.get("doc_type", ""),
            "confidence": rec.get("confidence", ""),
            "issuer": rec.get("issuer", ""),
            "scalar_fields": scalar_fields,
            "notes": doc_overrides.get("notes", ""),
        })
    return out


def _build_export_csv(records: list[dict], overrides: dict) -> str:
    """Return a CSV string with base columns + all unique key_fields expanded as columns."""
    base_cols = ["file_name", "doc_type", "confidence", "detected_year", "issuer", "sha256", "extraction_notes"]

    # Collect all unique key_field names across all records
    all_kf_keys: list[str] = []
    seen: set[str] = set()
    for rec in records:
        for k in rec.get("key_fields", {}):
            if k not in seen and k not in _SKIP_FIELDS:
                seen.add(k)
                all_kf_keys.append(k)

    fieldnames = base_cols + all_kf_keys + ["preparer_notes"]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()

    for rec in records:
        sha = rec.get("sha256", "")
        doc_overrides = overrides.get(sha, {})
        field_overrides = doc_overrides.get("fields", {})
        kf = rec.get("key_fields", {})

        row = {col: rec.get(col, "") for col in base_cols}
        for k in all_kf_keys:
            val = field_overrides.get(k, kf.get(k, ""))
            row[k] = "" if val is None else val
        row["preparer_notes"] = doc_overrides.get("notes", "")
        writer.writerow(row)

    return buf.getvalue()


_INDEX_TEMPLATE = """
<!doctype html>
<html><head><title>Tax Workpaper Dashboard</title>
<style>
  body { font-family: Arial, sans-serif; margin: 24px; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
  th { background-color: #f7f7f7; }
  .pill { display:inline-block; padding:2px 8px; border-radius:999px; background:#eef; margin-right:6px; }
  .tbl-link { font-size: 0.85em; white-space: nowrap; }
  .dash { color: #aaa; }
</style></head>
<body>
  <h1>Tax Workpaper Dashboard</h1>
  <p>Root: {{ root }}</p>
  <table>
    <tr>
      <th>Client</th><th>Docs</th><th>Tasks</th><th>Unknown</th><th>Errors</th><th>Extract Summary</th><th>Export</th><th>Overrides</th>
    </tr>
    {% for c in clients %}
    <tr>
      <td><a href="/client/{{ c.client }}">{{ c.client }}</a></td>
      <td>{{ c.document_count }}</td>
      <td>{{ c.task_count }}</td>
      <td>{{ c.unknown_count }}</td>
      <td>{{ c.error_count }}</td>
      <td>
        {% for k,v in c.extraction_counts.items() %}
        <span class="pill">{{ k }}: {{ v }}</span>
        {% endfor %}
      </td>
      <td>
        {% if c.has_outputs and c.document_count %}
        <a class="tbl-link" href="/client/{{ c.client }}/export.csv">↓ CSV</a>
        {% else %}<span class="dash">—</span>{% endif %}
      </td>
      <td>
        {% if c.has_outputs and c.document_count %}
        <a class="tbl-link" href="/client/{{ c.client }}#overrides">Edit</a>
        {% else %}<span class="dash">—</span>{% endif %}
      </td>
    </tr>
    {% endfor %}
  </table>
</body></html>
"""

_CLIENT_TEMPLATE = """
<!doctype html>
<html><head><title>{{ summary.client }} - Dashboard</title>
<style>
  body { font-family: Arial, sans-serif; margin: 24px; max-width: 960px; }
  h2 { border-bottom: 1px solid #ddd; padding-bottom: 4px; margin-top: 32px; margin-bottom: 8px; }
  .meta { color: #666; font-size: 0.9em; }
  .doc-card { border: 1px solid #ddd; border-radius: 6px; padding: 16px; margin-bottom: 20px; background: #fafafa; }
  .doc-card h3 { margin: 0 0 6px; font-size: 1em; }
  .badge { display:inline-block; padding:2px 8px; border-radius:999px; background:#dde; font-size:0.8em; margin-left:6px; }
  .fields-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; margin-top: 12px; }
  .field-row { display: flex; flex-direction: column; gap: 2px; }
  .field-row label { font-size: 0.8em; color: #555; }
  .field-row input, .field-row textarea { font-size: 0.9em; padding: 4px 6px; border: 1px solid #ccc; border-radius: 4px; width: 100%; box-sizing: border-box; }
  .field-row input.overridden { border-color: #e6a817; background: #fffbef; }
  .field-row .orig { font-size: 0.75em; color: #888; }
  .notes-row { margin-top: 10px; }
  .notes-row textarea { width: 100%; min-height: 60px; font-size: 0.85em; box-sizing: border-box; }
  .section-header { display: flex; align-items: baseline; justify-content: space-between; border-bottom: 1px solid #ddd; margin-top: 32px; padding-bottom: 4px; }
  .section-header h2 { margin: 0; border: none; padding: 0; }
  .btn { padding: 6px 14px; border: none; border-radius: 4px; cursor: pointer; font-size: 0.85em; text-decoration: none; }
  .btn-primary { background: #3a5bcc; color: #fff; }
  .btn-secondary { background: #eee; color: #333; }
  .btn:hover { opacity: 0.85; }
  .flash { background: #d4edda; border: 1px solid #c3e6cb; padding: 10px 16px; border-radius: 4px; margin-bottom: 16px; }
</style></head>
<body>
  <p><a href="/">← Back to clients</a></p>
  <h1>{{ summary.client }}</h1>
  <p class="meta">Documents: {{ summary.document_count }} | Unknown: {{ summary.unknown_count }} | Errors: {{ summary.error_count }}</p>

  {% if flash %}
  <div class="flash">{{ flash }}</div>
  {% endif %}

  <h2>Follow-up / Review Tasks</h2>
  {% if summary.tasks %}
  <ol>
    {% for task in summary.tasks %}
    <li>{{ task }}</li>
    {% endfor %}
  </ol>
  {% else %}
  <p>No follow-up tasks found. Generate workpapers first if needed.</p>
  {% endif %}

  <div class="section-header" id="overrides">
    <h2>Documents &amp; Field Overrides</h2>
    {% if records %}<a class="btn btn-secondary" href="/client/{{ summary.client }}/export.csv">↓ Download CSV Export</a>{% endif %}
  </div>
  {% if records %}
  <p class="meta">Edit any field below to override the extracted value. Empty fields revert to the extracted value. Add notes per document as needed.</p>
  <form method="post" action="/client/{{ summary.client }}/override">
    {% for rec in records %}
    <div class="doc-card">
      <h3>
        {{ rec.file_name }}
        <span class="badge">{{ rec.doc_type }}</span>
        {% if rec.issuer %}<span class="badge" style="background:#ede">{{ rec.issuer }}</span>{% endif %}
      </h3>
      <div class="meta">SHA: {{ rec.sha_short }} | Confidence: {{ rec.confidence }}</div>

      {% if rec.scalar_fields %}
      <div class="fields-grid">
        {% for f in rec.scalar_fields %}
        <div class="field-row">
          <label for="f__{{ rec.sha256 }}__{{ f.name }}">{{ f.name }}</label>
          <input
            type="{{ 'number' if f.is_numeric else 'text' }}"
            {% if f.is_numeric %}step="0.01"{% endif %}
            id="f__{{ rec.sha256 }}__{{ f.name }}"
            name="f__{{ rec.sha256 }}__{{ f.name }}"
            value="{{ f.override if f.override is not none else (f.original if f.original is not none else '') }}"
            {% if f.override is not none %}class="overridden"{% endif %}
          >
          {% if f.override is not none %}
          <span class="orig">extracted: {{ f.original }}</span>
          {% else %}
          <span class="orig">&nbsp;</span>
          {% endif %}
        </div>
        {% endfor %}
      </div>
      {% endif %}

      <div class="notes-row">
        <label for="n__{{ rec.sha256 }}"><strong>Preparer notes</strong></label>
        <textarea id="n__{{ rec.sha256 }}" name="n__{{ rec.sha256 }}">{{ rec.notes }}</textarea>
      </div>
    </div>
    {% endfor %}

    <button type="submit" class="btn btn-primary">Save Overrides</button>
  </form>
  {% else %}
  <p>No document records found. Run workpaper generation first.</p>
  {% endif %}

  <h2>Workpaper Files</h2>
  <ul>
    <li>{{ summary.workpapers_dir / 'Return_Prep_Checklist.md' }}</li>
    <li>{{ summary.workpapers_dir / 'Questions_For_Client.md' }}</li>
    <li>{{ summary.workpapers_dir / 'Document_Index.csv' }}</li>
    <li>{{ summary.workpapers_dir / 'Data_Extract.json' }}</li>
    <li>{{ summary.workpapers_dir / 'Prior_Year_Comparison.md' }}</li>
  </ul>
</body></html>
"""


def create_app(root: Path):
    try:
        from flask import Flask, abort, redirect, render_template_string, request, url_for, Response
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Flask is required for the web UI. Install with: pip install flask") from exc

    app = Flask(__name__)

    @app.get("/")
    def index():
        clients = list_client_summaries(root)
        return render_template_string(_INDEX_TEMPLATE, clients=clients, root=str(root))

    @app.get("/client/<client_name>")
    def client_detail(client_name: str):
        client_dir = root / client_name
        if not client_dir.exists() or not client_dir.is_dir():
            abort(404)
        summary = build_client_summary(client_dir)
        wp_dir = client_dir / "_workpapers"
        raw_records = load_document_records(wp_dir / "Document_Index.csv")
        overrides = _load_overrides(wp_dir)
        records = _prepare_records(raw_records, overrides)
        flash = request.args.get("saved")
        return render_template_string(
            _CLIENT_TEMPLATE,
            summary=summary,
            records=records,
            flash="Overrides saved." if flash else None,
        )

    @app.post("/client/<client_name>/override")
    def save_override(client_name: str):
        client_dir = root / client_name
        if not client_dir.exists() or not client_dir.is_dir():
            abort(404)
        wp_dir = client_dir / "_workpapers"
        if not wp_dir.exists():
            abort(404)

        overrides = _load_overrides(wp_dir)

        for key, value in request.form.items():
            value = value.strip()
            if key.startswith("f__"):
                # f__<sha256>__<field_name>
                parts = key.split("__", 2)
                if len(parts) != 3:
                    continue
                _, sha256, field_name = parts
                if sha256 not in overrides:
                    overrides[sha256] = {"fields": {}, "notes": ""}
                if value:
                    overrides[sha256]["fields"][field_name] = value
                else:
                    overrides[sha256]["fields"].pop(field_name, None)
            elif key.startswith("n__"):
                sha256 = key[3:]
                if sha256 not in overrides:
                    overrides[sha256] = {"fields": {}, "notes": ""}
                overrides[sha256]["notes"] = value

        # Drop entries with no data
        overrides = {
            k: v for k, v in overrides.items()
            if v.get("fields") or v.get("notes")
        }

        _save_overrides(wp_dir, overrides)
        return redirect(url_for("client_detail", client_name=client_name, saved="1"))

    @app.get("/client/<client_name>/export.csv")
    def export_csv(client_name: str):
        client_dir = root / client_name
        if not client_dir.exists() or not client_dir.is_dir():
            abort(404)
        wp_dir = client_dir / "_workpapers"
        raw_records = load_document_records(wp_dir / "Document_Index.csv")
        overrides = _load_overrides(wp_dir)
        csv_text = _build_export_csv(raw_records, overrides)
        return Response(
            csv_text,
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{client_name}_export.csv"'},
        )

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Local web dashboard for tax workpapers")
    parser.add_argument("--root", required=True, help="Root folder with client subfolders")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8787, type=int)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    app = create_app(Path(args.root))
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
