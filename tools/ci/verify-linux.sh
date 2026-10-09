#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

ARACHNEL_VERSION="${ARACHNEL_VERSION:-0.1.47}"
QT_VERSION="${QT_VERSION:-6.11.1}"
# aqtinstall arch id vs output directory name differ (linux_gcc_64 -> .../gcc_64/).
QT_AQT_ARCH="${QT_LINUX_ARCH:-linux_gcc_64}"
QT_DIR_NAME="${QT_DIR_NAME:-gcc_64}"

echo "=== Verify plugins on Linux (Arachnel v${ARACHNEL_VERSION}, Qt ${QT_VERSION}) ==="

SUDO=""
[[ "$(id -u)" -eq 0 ]] || SUDO="sudo"
${SUDO} apt-get update -qq
${SUDO} apt-get install -y --no-install-recommends \
  ca-certificates curl file python3 python3-venv binutils unzip

# Packages to check: arguments, otherwise every .arach in the repo root.
if (($# > 0)); then
  # Absolute paths: the script changes directory below.
  PACKAGES=()
  for pkg in "$@"; do PACKAGES+=("$(realpath "${pkg}")"); done
else
  mapfile -t PACKAGES < <(find "${ROOT}" -maxdepth 1 -name '*.arach' -type f | sort)
fi
if ((${#PACKAGES[@]} == 0)); then
  echo "No .arach packages to verify"
  exit 0
fi

WORKDIR="${VERIFY_WORKDIR:-${ROOT}/.ci-verify}"
mkdir -p "${WORKDIR}"
cd "${WORKDIR}"

APPIMG="Arachnel-${ARACHNEL_VERSION}-x86_64.AppImage"
if [[ ! -f "${APPIMG}" ]]; then
  URL="https://github.com/BadKiko/Arachnel/releases/download/v${ARACHNEL_VERSION}/${APPIMG}"
  echo "Downloading ${URL}"
  curl -fsSL -o "${APPIMG}" "${URL}"
fi
chmod +x "${APPIMG}"
./"${APPIMG}" --appimage-extract >/dev/null

# Qt from aqt supplements AppImage libs (plugins link against the same Qt minor).
AQT_VENV="${WORKDIR}/aqt-venv"
if [[ ! -x "${AQT_VENV}/bin/aqt" ]]; then
  python3 -m venv "${AQT_VENV}"
  "${AQT_VENV}/bin/pip" install --upgrade pip aqtinstall
fi
QT_BASE="${WORKDIR}/qt"
QT_PATH="${QT_BASE}/${QT_VERSION}/${QT_DIR_NAME}"
if [[ ! -f "${QT_PATH}/lib/libQt6Core.so" ]]; then
  "${AQT_VENV}/bin/aqt" install-qt linux desktop "${QT_VERSION}" "${QT_AQT_ARCH}" \
    -m qtshadertools qtmultimedia \
    -O "${QT_BASE}"
fi

# Prefer aqt Qt over AppImage libs so plugins linked against Qt 6.11 resolve
# Qt_6.11 symbols (AppImage may ship an older soname-compatible Core).
RUNTIME_DIRS=(
  "${QT_PATH}/lib"
  "${WORKDIR}/squashfs-root/usr/lib"
)

ARGS=(python3 "${ROOT}/tools/verify_plugins.py" --platform linux)
for dir in "${RUNTIME_DIRS[@]}"; do
  ARGS+=(--runtime-dir "${dir}")
done
ARGS+=("${PACKAGES[@]}")

echo "Running: ${ARGS[*]}"
"${ARGS[@]}"
