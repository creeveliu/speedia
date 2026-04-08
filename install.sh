#!/usr/bin/env bash
set -euo pipefail

REPO_OWNER="creeveliu"
REPO_NAME="speedia"
INSTALL_BIN_DIR="${HOME}/.local/bin"
INSTALL_ROOT="${HOME}/.local/share/speedia"
INSTALL_PATH="${INSTALL_BIN_DIR}/speedia"

platform="$(uname -s)"
arch="$(uname -m)"

case "${platform}-${arch}" in
  Darwin-arm64)
    asset="speedia-darwin-arm64.tar.gz"
    ;;
  Darwin-x86_64)
    asset="speedia-darwin-amd64.tar.gz"
    ;;
  Linux-x86_64)
    asset="speedia-linux-amd64.tar.gz"
    ;;
  *)
    echo "Unsupported platform: ${platform}-${arch}" >&2
    exit 1
    ;;
esac

url="https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/latest/download/${asset}"
tmp_archive="${INSTALL_ROOT}/speedia.tar.gz.tmp"
tmp_extract_dir="${INSTALL_ROOT}/.extract"
version_dir="${INSTALL_ROOT}/current"

mkdir -p "${INSTALL_BIN_DIR}" "${INSTALL_ROOT}"
echo "[info] Downloading ${asset}"
curl -fsSL "${url}" -o "${tmp_archive}"
rm -rf "${tmp_extract_dir}" "${version_dir}"
mkdir -p "${tmp_extract_dir}"
tar -xzf "${tmp_archive}" -C "${tmp_extract_dir}"
mv "${tmp_extract_dir}/speedia" "${version_dir}"
rm -f "${tmp_archive}"
rm -rf "${tmp_extract_dir}"
ln -sfn "${version_dir}/speedia" "${INSTALL_PATH}"
echo "[done] Installed to ${INSTALL_PATH}"

case ":${PATH}:" in
  *":${INSTALL_BIN_DIR}:"*) ;;
  *)
    echo "[warn] ${INSTALL_BIN_DIR} is not in PATH"
    echo "Add this to your shell profile:"
    echo "export PATH=\"${INSTALL_BIN_DIR}:\$PATH\""
    ;;
esac
