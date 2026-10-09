#!/usr/bin/env python3
"""Move plugin builds that still live on GitLab package registries to GitHub Releases.

stage : download every build in plugins.json whose URL is on gitlab.com, check its sha256 and put
        it in mirror/<tag>/<asset>; prints mirror/manifest.json
apply : rewrite those URLs in plugins.json to the GitHub release URLs (same bytes, same sha256)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "plugins.json"
MIRROR = ROOT / "mirror"
REPO = "BadKikoSecond/arachnel_plugins_sourcelist"
ASSET = {"freetp": "freetp.arach", "steamidra": "steam.arach"}
REPOSITORY = {
    "freetp": "https://github.com/BadKikoSecond/arachnel_freetp_plugin",
    "steamidra": "https://github.com/BadKikoSecond/arachnel_plugin_steamidra",
}


def rows():
    doc = json.loads(INDEX.read_text(encoding="utf-8"))
    for plugin in doc["plugins"]:
        for build in plugin.get("builds") or []:
            yield doc, plugin, build


def release_url(tag: str, asset: str) -> str:
    return f"https://github.com/{REPO}/releases/download/{tag}/{asset}"


def tag_for(plugin: dict, build: dict) -> str:
    return f"legacy-{plugin['id']}-{build['version']}"


def stage() -> int:
    shutil.rmtree(MIRROR, ignore_errors=True)
    manifest = []
    seen = set()
    for _, plugin, build in rows():
        url = str(build.get("url") or "")
        if "gitlab.com/" not in url:
            continue
        tag, asset = tag_for(plugin, build), ASSET[plugin["id"]]
        if tag in seen:
            continue
        seen.add(tag)
        dest = MIRROR / tag / asset
        dest.parent.mkdir(parents=True)
        h = hashlib.sha256()
        req = urllib.request.Request(url, headers={"User-Agent": "arachnel-sourcelist"})
        with urllib.request.urlopen(req, timeout=300) as r, dest.open("wb") as f:
            for chunk in iter(lambda: r.read(1 << 20), b""):
                h.update(chunk)
                f.write(chunk)
        if h.hexdigest() != str(build["sha256"]).lower():
            print(f"sha256 mismatch for {url}: {h.hexdigest()} != {build['sha256']}", file=sys.stderr)
            return 1
        manifest.append({"tag": tag, "asset": asset, "path": str(dest.relative_to(ROOT)), "old": url,
                         "new": release_url(tag, asset), "title": f"{plugin['name']} {build['version']} (mirrored from GitLab)"})
        print(f"staged {tag}: {dest.stat().st_size} bytes")
    (MIRROR / "manifest.json").parent.mkdir(exist_ok=True)
    (MIRROR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


def apply() -> int:
    doc = json.loads(INDEX.read_text(encoding="utf-8"))
    changed = 0
    for plugin in doc["plugins"]:
        if plugin["id"] in REPOSITORY and plugin.get("repository") != REPOSITORY[plugin["id"]]:
            plugin["repository"] = REPOSITORY[plugin["id"]]
            changed += 1
        by_url = {}
        for build in plugin.get("builds") or []:
            if "gitlab.com/" in str(build.get("url") or ""):
                new = release_url(tag_for(plugin, build), ASSET[plugin["id"]])
                by_url[build["url"]] = new
                build["url"] = new
                changed += 1
        if plugin.get("url") in by_url:
            plugin["url"] = by_url[plugin["url"]]
    INDEX.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"rewrote {changed} field(s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["stage", "apply"])
    args = ap.parse_args()
    return stage() if args.mode == "stage" else apply()


if __name__ == "__main__":
    raise SystemExit(main())
