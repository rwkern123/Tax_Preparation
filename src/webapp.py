from __future__ import annotations

import argparse
from pathlib import Path

from src.dashboard import build_client_summary, list_client_summaries


def create_app(root: Path):
    try:
        from flask import Flask, abort, render_template_string
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Flask is required for the web UI. Install with: pip install flask") from exc

    app = Flask(__name__)

    INDEX_TEMPLATE = """
    <!doctype html>
    <html><head><title>Tax Workpaper Dashboard</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 24px; }
      table { border-collapse: collapse; width: 100%; }
      th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
      th { background-color: #f7f7f7; }
      .pill { display:inline-block; padding:2px 8px; border-radius:999px; background:#eef; margin-right:6px; }
    </style></head>
    <body>
      <h1>Tax Workpaper Dashboard</h1>
      <p>Root: {{ root }}</p>
      <table>
        <tr>
          <th>Client</th><th>Docs</th><th>Tasks</th><th>Unknown</th><th>Errors</th><th>Extract Summary</th>
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
        </tr>
        {% endfor %}
      </table>
    </body></html>
    """

    CLIENT_TEMPLATE = """
    <!doctype html>
    <html><head><title>{{ summary.client }} - Dashboard</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 24px; }
      li { margin-bottom: 8px; }
      .meta { color:#666; }
    </style></head>
    <body>
      <p><a href="/">← Back to clients</a></p>
      <h1>{{ summary.client }}</h1>
      <p class="meta">Documents: {{ summary.document_count }} | Unknown: {{ summary.unknown_count }} | Errors: {{ summary.error_count }}</p>
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
      <h2>Open Workpaper Files</h2>
      <ul>
        <li>{{ summary.workpapers_dir / 'Return_Prep_Checklist.md' }}</li>
        <li>{{ summary.workpapers_dir / 'Questions_For_Client.md' }}</li>
        <li>{{ summary.workpapers_dir / 'Document_Index.csv' }}</li>
        <li>{{ summary.workpapers_dir / 'Data_Extract.json' }}</li>
        <li>{{ summary.workpapers_dir / 'Prior_Year_Comparison.md' }}</li>
      </ul>
    </body></html>
    """

    @app.get("/")
    def index():
      clients = list_client_summaries(root)
      return render_template_string(INDEX_TEMPLATE, clients=clients, root=str(root))

    @app.get("/client/<client_name>")
    def client(client_name: str):
      client_dir = root / client_name
      if not client_dir.exists() or not client_dir.is_dir():
          abort(404)
      summary = build_client_summary(client_dir)
      return render_template_string(CLIENT_TEMPLATE, summary=summary)

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
