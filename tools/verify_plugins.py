#!/usr/bin/env python3
"""Verify .arach plugin packages structure and native library load."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def find_plugin_root(extract_dir: Path) -> Path:
    candidates = sorted(
        extract_dir.rglob("plugin.json"),
        key=lambda p: (len(p.parts), len(str(p))),
    )
    if not candidates:
        raise ValueError("plugin.json not found inside archive")
    return candidates[0].parent


def read_plugin_json(arach: Path) -> dict:
    with zipfile.ZipFile(arach, "r") as zf:
        names = [n for n in zf.namelist() if n.endswith("plugin.json") and not n.endswith("/")]
        if not names:
            raise ValueError(f"{arach.name}: no plugin.json")
        names.sort(key=lambda n: (n.count("/"), len(n)))
        data = json.loads(zf.read(names[0]).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{arach.name}: plugin.json is not an object")
        return data


def resolve_library(root: Path, library_base: str, os_name: str) -> Path:
    if os_name == "linux":
        names = [f"lib{library_base}.so"]
    elif os_name == "windows":
        names = [f"{library_base}.dll", f"lib{library_base}.dll"]
    else:
        raise ValueError(f"unsupported platform: {os_name}")

    for name in names:
        path = root / name
        if path.is_file():
            return path
    raise FileNotFoundError(
        f"native library not found in {root} (expected one of: {', '.join(names)})"
    )


def required_exports() -> list[str]:
    return [
        "arachnel_plugin_api_version",
        "arachnel_plugin_create",
        "arachnel_plugin_destroy",
    ]


def check_exports_linux(lib: Path) -> None:
    tool = "llvm-nm" if shutil.which("llvm-nm") else "nm"
    if not shutil.which(tool):
        return
    out = subprocess.run(
        [tool, "-D", "--defined-only", str(lib)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for symbol in required_exports():
        if symbol not in out:
            raise RuntimeError(f"{lib.name}: missing export {symbol}")


def check_exports_windows(lib: Path) -> None:
    dumpbin = shutil.which("dumpbin")
    if not dumpbin:
        return
    out = subprocess.run(
        [dumpbin, "/exports", str(lib)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for symbol in required_exports():
        if symbol not in out:
            raise RuntimeError(f"{lib.name}: missing export {symbol}")


def verify_ldd_linux(lib: Path, runtime_dirs: list[Path]) -> None:
    env = os.environ.copy()
    ld_parts = [str(d) for d in runtime_dirs if d.is_dir()]
    if ld_parts:
        prev = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = ":".join(ld_parts + ([prev] if prev else []))

    proc = subprocess.run(["ldd", str(lib)], capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"ldd failed for {lib}:\n{proc.stderr or proc.stdout}")
    missing = [
        line.strip()
        for line in proc.stdout.splitlines()
        if "not found" in line.lower()
    ]
    if missing:
        raise RuntimeError(f"{lib.name}: unresolved dependencies:\n" + "\n".join(missing))


def load_library_linux(lib: Path, runtime_dirs: list[Path]) -> None:
    env = os.environ.copy()
    ld_parts = [str(d) for d in runtime_dirs if d.is_dir()]
    if ld_parts:
        prev = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = ":".join(ld_parts + ([prev] if prev else []))

    # dlopen in a child process so LD_LIBRARY_PATH is applied by the dynamic linker.
    script = f"""
import ctypes
lib = {str(lib)!r}
handle = ctypes.CDLL(lib)
symbols = {required_exports()!r}
missing = [s for s in symbols if not hasattr(handle, s)]
if missing:
    raise SystemExit("missing exports: " + ", ".join(missing))
"""
    proc = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "dlopen failed").strip()
        raise RuntimeError(f"{lib.name}: {msg}")


def load_library_windows(lib: Path, runtime_dirs: list[Path]) -> None:
    import ctypes

    if hasattr(os, "add_dll_directory"):
        handles = []
        for directory in runtime_dirs:
            if directory.is_dir():
                handles.append(os.add_dll_directory(str(directory.resolve())))
        try:
            ctypes.WinDLL(str(lib.resolve()))
        finally:
            for handle in handles:
                handle.close()
    else:
        path_parts = [str(d) for d in runtime_dirs if d.is_dir()]
        os.environ["PATH"] = ";".join(path_parts + [os.environ.get("PATH", "")])
        ctypes.WinDLL(str(lib.resolve()))


def verify_arach(
    arach: Path,
    *,
    os_name: str,
    runtime_dirs: list[Path],
    skip_load: bool,
) -> None:
    meta = read_plugin_json(arach)
    plugin_id = str(meta.get("id", "")).strip()
    library_base = str(meta.get("library", "")).strip()
    if not plugin_id or not library_base:
        raise ValueError(f"{arach.name}: plugin.json missing id/library")

    with tempfile.TemporaryDirectory(prefix="arach-verify-") as tmp:
        extract_dir = Path(tmp)
        with zipfile.ZipFile(arach, "r") as zf:
            zf.extractall(extract_dir)
        root = find_plugin_root(extract_dir)
        lib = resolve_library(root, library_base, os_name)

        if os_name == "linux":
            check_exports_linux(lib)
            if not skip_load:
                verify_ldd_linux(lib, runtime_dirs)
                load_library_linux(lib, runtime_dirs)
        elif os_name == "windows":
            check_exports_windows(lib)
            if not skip_load:
                load_library_windows(lib, runtime_dirs)
        else:
            raise ValueError(os_name)

    print(f"OK {arach.name} ({plugin_id} {meta.get('version', '?')})")


def default_runtime_dirs(os_name: str, runtime_root: Path | None) -> list[Path]:
    if runtime_root is None:
        return []
    root = runtime_root.resolve()
    if os_name == "linux":
        candidates = [
            root / "squashfs-root" / "usr" / "lib",
            root / "usr" / "lib",
            root / "lib",
        ]
    else:
        candidates = [
            root,
            root / "bin",
        ]
    return [p for p in candidates if p.is_dir()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", nargs="+", type=Path, help=".arach files to verify")
    parser.add_argument(
        "--platform",
        choices=("linux", "windows", "auto"),
        default="auto",
        help="host platform to verify (default: auto)",
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=None,
        help="Arachnel AppImage extract dir (linux) or install dir (windows)",
    )
    parser.add_argument(
        "--runtime-dir",
        action="append",
        type=Path,
        default=[],
        help="Extra library search path (repeatable)",
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="structure/export checks only (no dlopen/LoadLibrary)",
    )
    args = parser.parse_args()

    os_name = args.platform
    if os_name == "auto":
        system = platform.system().lower()
        if system == "linux":
            os_name = "linux"
        elif system == "windows":
            os_name = "windows"
        else:
            print(f"unsupported host OS: {system}", file=sys.stderr)
            return 2

    runtime_dirs = list(args.runtime_dir) + default_runtime_dirs(os_name, args.runtime_root)

    failed = False
    for package in args.packages:
        if not package.is_file():
            print(f"FAIL missing file: {package}", file=sys.stderr)
            failed = True
            continue
        try:
            verify_arach(
                package,
                os_name=os_name,
                runtime_dirs=runtime_dirs,
                skip_load=args.skip_load,
            )
        except Exception as exc:  # noqa: BLE001 — CI verifier reports all failures
            print(f"FAIL {package.name}: {exc}", file=sys.stderr)
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
