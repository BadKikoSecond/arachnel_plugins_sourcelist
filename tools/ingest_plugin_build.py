#!/usr/bin/env python3
"""Merge one plugin build into plugins.json (schema v2).

Used by plugin release CI to publish without hand-editing the index.

Examples:
  python tools/ingest_plugin_build.py \\
    --arach /path/steam.arach \\
    --url https://github.com/.../releases/download/v0.6.22/steam.arach \\
    --min-arachnel 0.1.34 \\
    --abi-token v0.1.34a

  # Also refresh the repo-root mirror package (optional, large for steam):
  python tools/ingest_plugin_build.py --arach steam.arach --mirror-as steam.arach
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from generate_plugins_index import (  # noqa: E402
    OUT,
    build_from_arach,
    flatten_plugin,
    load_previous,
    merge_builds,
    version_key,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arach", type=Path, required=True, help="Path to .arach package")
    ap.add_argument("--url", default="", help="Download URL (defaults to raw sourcelist URL)")
    ap.add_argument("--min-arachnel", default="", help="Override minArachnel")
    ap.add_argument("--max-arachnel", default="", help="Override maxArachnel (empty = no upper bound)")
    ap.add_argument("--abi-token", default="", help="Override abiToken / SDK tag")
    ap.add_argument(
        "--mirror-as",
        default="",
        help="Copy .arach into sourcelist root under this filename (e.g. steam.arach)",
    )
    ap.add_argument(
        "--no-write",
        action="store_true",
        help="Print resulting plugin entry only",
    )
    args = ap.parse_args()

    arach: Path = args.arach.resolve()
    if not arach.is_file():
        print(f"missing package: {arach}", file=sys.stderr)
        return 1

    if args.mirror_as:
        dest = ROOT / Path(args.mirror_as).name
        if arach.resolve() != dest.resolve():
            shutil.copy2(arach, dest)
            print(f"mirrored -> {dest}")
            arach = dest

    plugin_id, meta, build = build_from_arach(arach, url=args.url.strip() or None)
    if args.min_arachnel.strip():
        build["minArachnel"] = args.min_arachnel.strip()
    if args.max_arachnel is not None and args.max_arachnel != "":
        # Explicit empty string clears upper bound when passed as ""
        build["maxArachnel"] = args.max_arachnel.strip()
    if args.abi_token.strip():
        build["abiToken"] = args.abi_token.strip()

    previous = load_previous()
    plugins_in = previous.get("plugins") if isinstance(previous.get("plugins"), list) else []
    by_id: dict[str, dict] = {}
    builds_by_id: dict[str, list[dict]] = {}

    for row in plugins_in:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        pid = str(row["id"])
        by_id[pid] = {
            "id": pid,
            "name": row.get("name") or pid,
            "description": row.get("description") or "",
            "iconName": row.get("iconName") or "extension",
            "repository": row.get("repository") or "",
        }
        old_builds = row.get("builds")
        if isinstance(old_builds, list) and old_builds:
            builds_by_id[pid] = [b for b in old_builds if isinstance(b, dict)]
        else:
            builds_by_id[pid] = [
                {
                    "version": str(row.get("version") or "0.0.0"),
                    "apiVersion": int(row.get("apiVersion") or 0),
                    "minArachnel": str(row.get("minArachnel") or "0.0.0"),
                    "maxArachnel": str(row.get("maxArachnel") or ""),
                    "url": str(row.get("url") or ""),
                    "sha256": str(row.get("sha256") or ""),
                    "size": row.get("size") or 0,
                    "platforms": list(row.get("platforms") or ["windows", "linux"]),
                    "abiToken": str(row.get("abiToken") or f"api={int(row.get('apiVersion') or 0)}"),
                    "file": row.get("file"),
                }
            ]

    by_id[plugin_id] = meta
    builds_by_id[plugin_id] = merge_builds(builds_by_id.get(plugin_id, []), build)

    plugins = [
        flatten_plugin(by_id[pid], builds_by_id.get(pid, []))
        for pid in sorted(by_id.keys(), key=lambda i: (by_id[i].get("name") or i).lower())
    ]

    doc = {
        "schemaVersion": 2,
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plugins": plugins,
    }

    if args.no_write:
        target = next(p for p in plugins if p["id"] == plugin_id)
        print(json.dumps(target, ensure_ascii=False, indent=2))
        return 0

    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"ingested {plugin_id} {build['version']} "
        f"(builds={len(builds_by_id[plugin_id])}, key={version_key(build['version'])})"
    )
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
