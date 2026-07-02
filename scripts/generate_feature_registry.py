#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from app.signals.registry import render_feature_registry_markdown

    output_path = repo_root / "docs" / "FEATURE_REGISTRY.md"
    output_path.write_text(render_feature_registry_markdown(), encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
