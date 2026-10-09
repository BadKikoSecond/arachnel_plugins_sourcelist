#!/usr/bin/env python3
"""Find plugin releases on GitHub that are not in plugins.json yet and download them.

Replaces the GitLab "trigger a pipeline from the plugin project" bridge: the sourcelist looks at
the plugin repos' public Releases itself (listed in tools/plugin_sources.json), so publishing needs
no cross-repo secret. A plugin release workflow may still send a `repository_dispatch` for an
instant update; that goes through `--explicit` below.

Output: pending/<id>-<tag>/<asset> plus pending/pending.json:
  [{"id","tag","url","file","dir","minArachnel","maxArachnel","abiToken"}]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from generate_plugins_index import OUT, version_key  # noqa: E402

PENDING = ROOT / "pending"
SEMVER = re.compile(r"^v?\d+\.\d+\.\d+(-[A-Za-z0-9._]+)?$")


def http_json(url: str):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "arachnel-sourcelist"})
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "arachnel-sourcelist"})
    with urllib.request.urlopen(req, timeout=300) as r, dest.open("wb") as f:
        shutil.copyfileobj(r, f)
    if dest.stat().st_size == 0:
        raise RuntimeError(f"empty download: {url}")


def load_index() -> dict:
    if OUT.is_file():
        return json.loads(OUT.read_text(encoding="utf-8"))
    return {"plugins": []}


def known(index: dict, plugin_id: str) -> tuple[set[str], tuple]:
    urls: set[str] = set()
    newest: tuple = (0,)
    for row in index.get("plugins", []):
        if row.get("id") != plugin_id:
            continue
        builds = row.get("builds") or [row]
        for b in builds:
            if b.get("url"):
                urls.add(str(b["url"]))
            newest = max(newest, version_key(str(b.get("version") or "")))
    return urls, newest


def find_pending(sources: list[dict], index: dict, force_latest: bool) -> list[dict]:
    out: list[dict] = []
    for src in sources:
        try:
            releases = http_json(f"https://api.github.com/repos/{src['repo']}/releases?per_page=10")
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"::warning::cannot list releases of {src['repo']}: {exc}")
            continue
        urls, newest = known(index, src["id"])
        found: list[dict] = []
        for rel in releases:
            if rel.get("draft") or rel.get("prerelease") or not SEMVER.match(rel.get("tag_name", "")):
                continue
            asset = next((a for a in rel.get("assets", []) if a["name"] == src["asset"]), None)
            if not asset:
                continue
            url = asset["browser_download_url"]
            if url in urls or version_key(rel["tag_name"]) < newest:
                continue
            found.append({"id": src["id"], "tag": rel["tag_name"], "url": url, "file": src["asset"],
                          "minArachnel": src.get("minArachnel", ""), "maxArachnel": src.get("maxArachnel", ""),
                          "abiToken": src.get("abiToken", "")})
        if not found and force_latest:
            # Diagnostics: re-run the whole verify/ingest chain on the newest stable release.
            for rel in releases:
                asset = next((a for a in rel.get("assets", []) if a["name"] == src["asset"]), None)
                if asset and not rel.get("draft") and not rel.get("prerelease") and SEMVER.match(rel["tag_name"]):
                    found.append({"id": src["id"], "tag": rel["tag_name"], "url": asset["browser_download_url"],
                                  "file": src["asset"], "minArachnel": src.get("minArachnel", ""),
                                  "maxArachnel": src.get("maxArachnel", ""), "abiToken": src.get("abiToken", "")})
                    break
        found.sort(key=lambda r: version_key(r["tag"]))
        out.extend(found)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force-latest", action="store_true", help="also pick the newest release when it is already indexed")
    ap.add_argument("--explicit-url", default="", help="ingest this exact package instead of polling")
    ap.add_argument("--explicit-id", default="")
    ap.add_argument("--explicit-file", default="")
    ap.add_argument("--explicit-tag", default="build")
    ap.add_argument("--min-arachnel", default="0.1.34")
    ap.add_argument("--max-arachnel", default="")
    ap.add_argument("--abi-token", default="develop")
    args = ap.parse_args()

    shutil.rmtree(PENDING, ignore_errors=True)
    PENDING.mkdir()
    if args.explicit_url:
        name = Path(args.explicit_file or Path(args.explicit_url).name).name
        pending = [{"id": args.explicit_id or Path(name).stem, "tag": args.explicit_tag, "url": args.explicit_url,
                    "file": name, "minArachnel": args.min_arachnel, "maxArachnel": args.max_arachnel,
                    "abiToken": args.abi_token}]
    else:
        sources = json.loads((ROOT / "tools" / "plugin_sources.json").read_text(encoding="utf-8"))["sources"]
        pending = find_pending(sources, load_index(), args.force_latest)

    for item in pending:
        d = PENDING / f"{item['id']}-{item['tag']}"
        item["dir"] = str(d.relative_to(ROOT))
        print(f"downloading {item['url']}")
        download(item["url"], d / item["file"])
    (PENDING / "pending.json").write_text(json.dumps(pending, indent=2) + "\n", encoding="utf-8")
    print(f"{len(pending)} pending release(s)")
    for item in pending:
        print(f"  {item['id']} {item['tag']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
