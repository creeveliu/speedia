#!/usr/bin/env bash
set -euo pipefail

REPO_OWNER="creeveliu"
REPO_NAME="speedia"
INSTALL_DIR="${HOME}/.local/bin"
INSTALL_PATH="${INSTALL_DIR}/speedia"

platform="$(uname -s)"
arch="$(uname -m)"

case "${platform}-${arch}" in
  Darwin-arm64)
    asset="speedia-darwin-arm64"
    ;;
  Darwin-x86_64)
    asset="speedia-darwin-amd64"
    ;;
  Linux-x86_64)
    asset="speedia-linux-amd64"
    ;;
  *)
    echo "Unsupported platform: ${platform}-${arch}" >&2
    exit 1
    ;;
esac

url="https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/latest/download/${asset}"
tmp_path="${INSTALL_PATH}.tmp"

mkdir -p "${INSTALL_DIR}"
echo "[info] Downloading ${asset}"
curl -fsSL "${url}" -o "${tmp_path}"
chmod +x "${tmp_path}"
mv "${tmp_path}" "${INSTALL_PATH}"
echo "[done] Installed to ${INSTALL_PATH}"

case ":${PATH}:" in
  *":${INSTALL_DIR}:"*) ;;
  *)
    echo "[warn] ${INSTALL_DIR} is not in PATH"
    echo "Add this to your shell profile:"
    echo "export PATH=\"${INSTALL_DIR}:\$PATH\""
    ;;
esac
