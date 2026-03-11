#!/usr/bin/env python3
"""
Launch the Tax Preparer Dashboard.

Usage:
  python run_preparer.py
  python run_preparer.py --port 8800 --debug

Set PREPARER_PASSWORD env var before first run (default: changeme).
The dashboard runs on http://127.0.0.1:8800 by default.
"""
import argparse
from preparer.app import create_app

parser = argparse.ArgumentParser(description="Tax Preparer Dashboard")
parser.add_argument("--port",  type=int, default=8800)
parser.add_argument("--host",  default="127.0.0.1")
parser.add_argument("--debug", action="store_true")
args = parser.parse_args()

app = create_app()
print(f"Preparer dashboard running at http://{args.host}:{args.port}")
print("Default password: changeme  (set PREPARER_PASSWORD env var to change)")
app.run(host=args.host, port=args.port, debug=args.debug)
