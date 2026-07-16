#!/usr/bin/env python3
"""Generate plugins.json from *.arach packages in the repo root."""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "plugins.json"

# Public raw URL base for files on the default branch.
RAW_BASE = "https://gitlab.com/BadKiko/arachnel-plugins-sourcelist/-/raw/main"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_plugin_json(arach: Path) -> dict:
    with zipfile.ZipFile(arach, "r") as zf:
        candidates = [n for n in zf.namelist() if n.endswith("plugin.json") and not n.endswith("/")]
        if not candidates:
            raise ValueError(f"{arach.name}: no plugin.json inside")
        # Prefer shallowest path
        candidates.sort(key=lambda n: (n.count("/"), len(n)))
        data = json.loads(zf.read(candidates[0]).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{arach.name}: plugin.json is not an object")
        return data


def detect_platforms(arach: Path) -> list[str]:
    platforms: set[str] = set()
    with zipfile.ZipFile(arach, "r") as zf:
        for name in zf.namelist():
            lower = name.lower()
            if lower.endswith(".dll"):
                platforms.add("windows")
            if lower.endswith(".so"):
                platforms.add("linux")
            if lower.endswith(".dylib"):
                platforms.add("macos")
    return sorted(platforms) or ["windows", "linux"]


def main() -> int:
    packages = sorted(ROOT.glob("*.arach"))
    plugins = []
    for arach in packages:
        meta = read_plugin_json(arach)
        plugin_id = str(meta.get("id", "")).strip()
        if not plugin_id:
            print(f"skip {arach.name}: missing id", file=sys.stderr)
            continue
        entry = {
            "id": plugin_id,
            "name": str(meta.get("name") or plugin_id),
            "description": str(meta.get("description") or ""),
            "version": str(meta.get("version") or "0.0.0"),
            "apiVersion": int(meta.get("apiVersion") or 0),
            "iconName": str(meta.get("iconName") or "extension"),
            "file": arach.name,
            "url": f"{RAW_BASE}/{arach.name}",
            "sha256": sha256_file(arach),
            "size": arach.stat().st_size,
            "platforms": detect_platforms(arach),
        }
        plugins.append(entry)
        print(f"  + {plugin_id} {entry['version']} ({arach.name})")

    plugins.sort(key=lambda p: p["name"].lower())
    doc = {
        "schemaVersion": 1,
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plugins": plugins,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(plugins)} plugins)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
