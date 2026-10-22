"""Vercel entry point: the whole Arba API as one Python function.

vercel.json sends every /api/... request here; FastAPI routes it by its original path.
The backend code is bundled from backend/ (see "includeFiles" in vercel.json).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402

__all__ = ["app"]
