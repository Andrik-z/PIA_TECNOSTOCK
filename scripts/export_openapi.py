"""python scripts/export_openapi.py -> docs/api/openapi.json"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/openapi_tmp.db")
from src.api.main import app  # noqa: E402

destino = Path(__file__).resolve().parents[1] / "docs" / "api" / "openapi.json"
destino.write_text(json.dumps(app.openapi(), indent=2, ensure_ascii=False), encoding="utf-8")
print("OpenAPI escrito en", destino)
