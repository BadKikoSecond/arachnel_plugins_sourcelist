#!/usr/bin/env python3
"""Ingest everything listed in pending/pending.json into plugins.json (oldest first)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    items = json.loads((ROOT / "pending" / "pending.json").read_text(encoding="utf-8"))
    for item in items:
        arach = ROOT / item["dir"] / item["file"]
        cmd = [sys.executable, str(ROOT / "tools" / "ingest_plugin_build.py"), "--arach", str(arach),
               "--url", item["url"], "--min-arachnel", item.get("minArachnel") or "0.1.34",
               "--abi-token", item.get("abiToken") or "develop"]
        if item.get("maxArachnel"):
            cmd += ["--max-arachnel", item["maxArachnel"]]
        print("::group::" + " ".join(cmd))
        rc = subprocess.call(cmd)
        print("::endgroup::")
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
