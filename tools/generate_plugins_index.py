#!/usr/bin/env python3
"""Generate plugins.json (schema v2) from *.arach packages + previous builds history."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "plugins.json"

# Public raw URL base for files on the default branch.
RAW_BASE = "https://gitlab.com/BadKiko/arachnel-plugins-sourcelist/-/raw/main"

KNOWN_REPOS = {
    "freetp": "https://github.com/PetWork/arachnel-plugin-freetp",
    "steamidra": "https://gitlab.com/BadKiko/arachnel-plugin-steamidra",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_plugin_json(arach: Path) -> dict:
    import zipfile

    with zipfile.ZipFile(arach, "r") as zf:
        candidates = [n for n in zf.namelist() if n.endswith("plugin.json") and not n.endswith("/")]
        if not candidates:
            raise ValueError(f"{arach.name}: no plugin.json inside")
        candidates.sort(key=lambda n: (n.count("/"), len(n)))
        data = json.loads(zf.read(candidates[0]).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{arach.name}: plugin.json is not an object")
        return data


def detect_platforms(arach: Path) -> list[str]:
    import zipfile

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


def version_key(ver: str) -> tuple:
    """Sort key for plugin versions like 0.4.7 / 1.0.18."""
    s = (ver or "").lstrip("vV").strip()
    nums: list[int] = []
    for part in re.split(r"[^\d]+", s):
        if part.isdigit():
            nums.append(int(part))
    return tuple(nums) if nums else (0,)


def build_from_arach(arach: Path, *, url: str | None = None) -> tuple[str, dict, dict]:
    meta = read_plugin_json(arach)
    plugin_id = str(meta.get("id", "")).strip()
    if not plugin_id:
        raise ValueError(f"{arach.name}: missing id")

    api_version = int(meta.get("apiVersion") or 0)
    version = str(meta.get("version") or "0.0.0")
    abi = str(meta.get("abiToken") or meta.get("sdkRef") or "").strip()
    if not abi:
        abi = f"api={api_version}"

    build = {
        "version": version,
        "apiVersion": api_version,
        "minArachnel": str(meta.get("minArachnel") or "0.0.0").strip() or "0.0.0",
        "maxArachnel": str(meta.get("maxArachnel") or "").strip(),
        "url": url or f"{RAW_BASE}/{arach.name}",
        "sha256": sha256_file(arach),
        "size": arach.stat().st_size,
        "platforms": detect_platforms(arach),
        "abiToken": abi,
        "file": arach.name,
    }

    plugin_meta = {
        "id": plugin_id,
        "name": str(meta.get("name") or plugin_id),
        "description": str(meta.get("description") or ""),
        "iconName": str(meta.get("iconName") or "extension"),
        "repository": str(meta.get("repository") or "").strip(),
    }
    return plugin_id, plugin_meta, build


def merge_builds(existing: list[dict], new_build: dict) -> list[dict]:
    """Keep history; replace same version or same sha256.

    Also drop older builds that pointed at the same repo-root mirror file/URL,
    because regenerating overwrites that package on disk.
    """
    out: list[dict] = []
    new_ver = str(new_build.get("version") or "")
    new_sha = str(new_build.get("sha256") or "").lower()
    new_file = str(new_build.get("file") or "")
    new_url = str(new_build.get("url") or "")
    for b in existing:
        if not isinstance(b, dict):
            continue
        if str(b.get("sha256") or "").lower() == new_sha:
            continue
        if str(b.get("version") or "") == new_ver:
            continue
        old_file = str(b.get("file") or "")
        old_url = str(b.get("url") or "")
        if new_file and old_file == new_file:
            continue
        if new_url and old_url == new_url:
            continue
        out.append(b)
    out.append(new_build)
    out.sort(key=lambda b: version_key(str(b.get("version") or "")), reverse=True)
    return out


def flatten_plugin(meta: dict, builds: list[dict]) -> dict:
    """Schema v2 entry with flat latest fields for older clients.

    Flat url/version prefer the newest API<=3 build so Arachnel builds that
    only read top-level fields keep installing a loadable package. New hosts
    pick from builds[] by appVersion + platform.
    """
    builds_sorted = sorted(
        [b for b in builds if isinstance(b, dict)],
        key=lambda b: version_key(str(b.get("version") or "")),
        reverse=True,
    )
    legacy = [b for b in builds_sorted if int(b.get("apiVersion") or 0) <= 3]
    flat_source = legacy[0] if legacy else (builds_sorted[0] if builds_sorted else {})
    latest = builds_sorted[0] if builds_sorted else {}
    entry = {
        "id": meta["id"],
        "name": meta.get("name") or meta["id"],
        "description": meta.get("description") or "",
        "iconName": meta.get("iconName") or "extension",
        # Flat fields: safest for old PluginCatalogService (no builds[]).
        "version": str(flat_source.get("version") or latest.get("version") or "0.0.0"),
        "apiVersion": int(flat_source.get("apiVersion") or latest.get("apiVersion") or 0),
        "url": str(flat_source.get("url") or latest.get("url") or ""),
        "sha256": str(flat_source.get("sha256") or latest.get("sha256") or ""),
        "size": flat_source.get("size") or latest.get("size") or 0,
        "platforms": list(
            flat_source.get("platforms") or latest.get("platforms") or ["windows", "linux"]
        ),
        "builds": builds_sorted,
    }
    if flat_source.get("file") or latest.get("file"):
        entry["file"] = flat_source.get("file") or latest.get("file")
    repo = str(meta.get("repository") or "").strip()
    if repo:
        entry["repository"] = repo
    return entry


def load_previous() -> dict:
    if not OUT.exists():
        return {}
    try:
        old = json.loads(OUT.read_text(encoding="utf-8"))
        return old if isinstance(old, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> int:
    previous = load_previous()
    previous_by_id: dict[str, dict] = {}
    for row in previous.get("plugins") or []:
        if isinstance(row, dict) and row.get("id"):
            previous_by_id[str(row["id"])] = row

    packages = sorted(ROOT.glob("*.arach"))
    # Optional versioned history under builds/
    builds_dir = ROOT / "builds"
    if builds_dir.is_dir():
        packages.extend(sorted(builds_dir.glob("*.arach")))

    by_id: dict[str, dict] = {}
    builds_by_id: dict[str, list[dict]] = {}

    # Seed from previous history
    for pid, row in previous_by_id.items():
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
            # Migrate schema v1 flat entry into a single build
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

    for arach in packages:
        try:
            plugin_id, meta, build = build_from_arach(arach)
        except Exception as exc:  # noqa: BLE001
            print(f"skip {arach.name}: {exc}", file=sys.stderr)
            continue
        by_id[plugin_id] = meta
        if not meta.get("repository"):
            prev_repo = previous_by_id.get(plugin_id, {}).get("repository")
            by_id[plugin_id]["repository"] = prev_repo or KNOWN_REPOS.get(plugin_id, "")
        builds_by_id[plugin_id] = merge_builds(builds_by_id.get(plugin_id, []), build)
        print(f"  + {plugin_id} {build['version']} ({arach.name})")

    plugins = [
        flatten_plugin(by_id[pid], builds_by_id.get(pid, []))
        for pid in sorted(by_id.keys(), key=lambda i: (by_id[i].get("name") or i).lower())
    ]

    previous_plugins = previous.get("plugins")
    previous_updated = previous.get("updatedAt")
    if previous_plugins == plugins and isinstance(previous_updated, str) and previous_updated:
        updated_at = previous_updated
    else:
        updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    doc = {
        "schemaVersion": 2,
        "updatedAt": updated_at,
        "plugins": plugins,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} (schema v2, {len(plugins)} plugins)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
