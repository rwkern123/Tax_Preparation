import sys
from pathlib import Path

# Ensure the project root is on the Python path
sys.path.insert(0, str(Path(__file__).parent))

from portal.app import create_app
import argparse


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Client Tax Preparation Portal")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", default=5050, type=int, help="Port to listen on (default: 5050)")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    args = parser.parse_args()

    app = create_app()
    print(f"Client Portal running at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    app.run(host=args.host, port=args.port, debug=args.debug)
