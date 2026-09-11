"""
Package init exists for one reason: load `.env` before any module reads the
environment.

`app.db` resolves DATABASE_URL at import time, so a dotenv load placed inside
main.py would run too late — the module is already imported by then.

`override=False` so a real environment variable always beats the file. In
compose the values arrive as env vars and there is no .env inside the container;
running uvicorn directly on the host, the file is what supplies them.
"""

from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is optional; compose supplies env vars directly
    pass
else:
    # api/app/__init__.py → repo root
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
