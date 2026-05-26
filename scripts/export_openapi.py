#!/usr/bin/env python3
"""Export the OpenAPI schema to docs/openapi.json for Swagger UI / codegen."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402


def main() -> None:
    out = ROOT / "docs" / "openapi.json"
    schema = app.openapi()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    paths = len(schema.get("paths", {}))
    print(f"Wrote {out} ({paths} paths, OpenAPI {schema.get('openapi', '?')})")


if __name__ == "__main__":
    main()
