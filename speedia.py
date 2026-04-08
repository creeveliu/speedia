#!/usr/bin/env python3
import argparse
import ast
import base64
import binascii
import html
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Sequence

import requests
from requests.exceptions import RequestException

DEFAULT_SECRET = "speedia"
REPO_OWNER = "creeveliu"
REPO_NAME = "speedia"
DEFAULT_VERSION = "0.1.2"
GROUP = ""  # 留空会自动选节点最多的组
LIMIT = 50  # 每轮测速节点数，先用 20~50 更稳

API = "http://127.0.0.1:19090"
HTTP_PROXY = "http://127.0.0.1:17893"
TEST_URL = "https://speed.cloudflare.com/__down?bytes=3000000"
MAX_TIME = 8

def get_managed_bin_dir() -> Path:
    return Path.home() / ".local" / "bin"


def get_managed_install_root() -> Path:
    return Path.home() / ".local" / "share" / "speedia"


def get_managed_launcher_path() -> Path:
    return get_managed_bin_dir() / "speedia"


def get_release_asset_name() -> str:
    sys_name = platform.system().lower()
    machine = platform.machine().lower()
    if sys_name == "darwin" and machine in {"arm64", "aarch64"}:
        return "speedia-darwin-arm64.tar.gz"
    if sys_name == "darwin" and machine in {"x86_64", "amd64"}:
        return "speedia-darwin-amd64.tar.gz"
    if sys_name == "linux" and machine in {"x86_64", "amd64"}:
        return "speedia-linux-amd64.tar.gz"
    raise RuntimeError(f"Unsupported install target: {sys_name}/{machine}")


def get_release_asset_url() -> str:
    return f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/latest/download/{get_release_asset_name()}"


def get_latest_release_api_url() -> str:
    return f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"


def get_display_version() -> str:
    return os.environ.get("SPEEDIA_VERSION", DEFAULT_VERSION)


def parse_latest_version_tag(tag: str) -> str:
    return tag[1:] if tag.startswith("v") else tag


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch speed test for Clash/Mihomo subscriptions")
    parser.add_argument("--version", action="version", version=f"%(prog)s {get_display_version()}")
    parser.add_argument("target", help="Subscription URL to test, or update/uninstall")
    args = parser.parse_args(argv)
    if args.target in {"update", "uninstall"}:
        args.command = args.target
        args.sub_url = None
    else:
        args.command = "test"
        args.sub_url = args.target
    return args


def download(url: str, out: Path) -> None:
    out.write_bytes(fetch_url_bytes(url))


def fetch_url_bytes(url: str) -> bytes:
    request_error = None
    try:
        response = requests.get(url, headers={"User-Agent": "batch-speedtest"}, timeout=60)
        response.raise_for_status()
        return response.content
    except RequestException as exc:
        request_error = exc
        # Some providers work with curl but fail with Python TLS stacks.
        cp = subprocess.run(
            ["curl", "-L", "--silent", "--show-error", url],
            capture_output=True,
            check=False,
        )
        if cp.returncode == 0 and cp.stdout:
            return cp.stdout
        curl_error = cp.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Failed to fetch subscription. requests: {request_error}; curl: {curl_error}") from exc


def get_cache_dir() -> Path:
    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg_cache_home).expanduser() if xdg_cache_home else Path.home() / ".cache"
    return base / "speedia"


def get_geoip_db() -> Path:
    cache_dir = get_cache_dir()
    geoip_path = cache_dir / "geoip.metadb"
    if geoip_path.exists():
        return geoip_path

    cache_dir.mkdir(parents=True, exist_ok=True)
    print("[info] Downloading geoip.metadb")
    download(
        "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.metadb",
        geoip_path,
    )
    return geoip_path


def get_mihomo_bin() -> Path:
    found = shutil_which("mihomo")
    if found:
        return Path(found)

    sys_name = platform.system().lower()
    machine = platform.machine().lower()
    asset = None
    if sys_name == "darwin" and machine in ("arm64", "aarch64"):
        asset = "mihomo-darwin-arm64-v1.19.23.gz"
    elif sys_name == "darwin" and machine in ("x86_64", "amd64"):
        asset = "mihomo-darwin-amd64-v1.19.23.gz"
    elif sys_name == "linux" and machine in ("x86_64", "amd64"):
        asset = "mihomo-linux-amd64-v1.19.23.gz"
    elif sys_name == "linux" and machine in ("arm64", "aarch64"):
        asset = "mihomo-linux-arm64-v1.19.23.gz"
    else:
        raise RuntimeError(f"Unsupported platform: {sys_name}/{machine}")

    url = f"https://github.com/MetaCubeX/mihomo/releases/download/v1.19.23/{asset}"
    cache_dir = get_cache_dir()
    gz_path = cache_dir / "mihomo.gz"
    bin_path = cache_dir / "mihomo"
    if bin_path.exists():
        return bin_path

    cache_dir.mkdir(parents=True, exist_ok=True)
    print(f"[info] Downloading mihomo: {asset}")
    download(url, gz_path)
    subprocess.run(["gunzip", "-f", str(gz_path)], check=True)
    bin_path.chmod(0o755)
    return bin_path


def shutil_which(cmd: str) -> str:
    return subprocess.run(
        ["bash", "-lc", f"command -v {cmd} || true"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


def patch_config(config_text: str) -> str:
    lines = config_text.splitlines()
    keys = {
        "secret:": f"secret: {DEFAULT_SECRET}",
        "port:": "port: 17890",
        "socks-port:": "socks-port: 17891",
        "redir-port:": "redir-port: 0",
        "mixed-port:": "mixed-port: 17893",
        "allow-lan:": "allow-lan: false",
        "external-controller:": "external-controller: 127.0.0.1:19090",
    }
    done = {k: False for k in keys}

    out = []
    for line in lines:
        stripped = line.strip()
        replaced = False
        for key, new_value in keys.items():
            if stripped.startswith(key):
                out.append(new_value)
                done[key] = True
                replaced = True
                break
        if not replaced:
            out.append(line)

    for key, new_value in keys.items():
        if not done[key]:
            out.append(new_value)

    return "\n".join(out) + "\n"


def decode_yaml_scalar(text: str) -> str:
    value = text.strip()
    if not value:
        return value
    if value[0] in ('"', "'") and value[-1:] == value[0]:
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return value[1:-1]
    return value


def extract_clash_proxies_block(config_text: str) -> tuple[list[str], list[str]]:
    lines = config_text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == "proxies:" and line == line.lstrip():
            start = i
            break
    if start is None:
        raise RuntimeError("Subscription does not contain a top-level proxies section")

    block = ["proxies:"]
    names = []
    current_item_started = False
    for line in lines[start + 1 :]:
        if line and line == line.lstrip():
            break
        if not line.strip():
            block.append(line)
            continue
        block.append(line)

        stripped = line.strip()
        if stripped.startswith("- "):
            current_item_started = True
            remainder = stripped[2:].strip()
            if remainder.startswith("name:"):
                names.append(decode_yaml_scalar(remainder.split(":", 1)[1]))
            else:
                match = re.search(r"(?:^|[,{]\s*)name:\s*([^,}]+)", remainder)
                if match:
                    names.append(decode_yaml_scalar(match.group(1)))
        elif current_item_started and stripped.startswith("name:"):
            names.append(decode_yaml_scalar(stripped.split(":", 1)[1]))

    deduped_names = [name for i, name in enumerate(names) if name and name not in names[:i]]
    if not deduped_names:
        raise RuntimeError("No proxy names found in Clash subscription")
    return block, deduped_names


def maybe_decode_base64_text(text: str) -> str | None:
    stripped = "".join(text.split())
    if not stripped:
        return None
    try:
        decoded = base64.b64decode(stripped + "=" * (-len(stripped) % 4), validate=False)
    except (binascii.Error, ValueError):
        return None
    try:
        return decoded.decode("utf-8")
    except UnicodeDecodeError:
        return decoded.decode("utf-8", errors="replace")


def parse_ss_uri(uri: str) -> dict:
    raw = uri[len("ss://") :]
    fragment = ""
    if "#" in raw:
        raw, fragment = raw.split("#", 1)
    name = urllib.parse.unquote(fragment) or "ss-node"
    query = ""
    if "?" in raw:
        raw, query = raw.split("?", 1)
    plugin_params = urllib.parse.parse_qs(query)

    if "@" in raw:
        userinfo, server_part = raw.rsplit("@", 1)
        decoded = base64.b64decode(userinfo + "=" * (-len(userinfo) % 4)).decode("utf-8")
        cipher, password = decoded.split(":", 1)
        server, port = server_part.rsplit(":", 1)
    else:
        decoded = base64.b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
        creds, server, port = decoded.rsplit("@", 1)[0], decoded.rsplit("@", 1)[1].rsplit(":", 1)[0], decoded.rsplit(":", 1)[1]
        cipher, password = creds.split(":", 1)

    proxy = {
        "name": name,
        "type": "ss",
        "server": server,
        "port": int(port),
        "cipher": cipher,
        "password": password,
        "udp": True,
    }
    plugin = plugin_params.get("plugin", [""])[0]
    if plugin:
        plugin_name, _, plugin_opts = plugin.partition(";")
        proxy["plugin"] = plugin_name
        opts = {}
        for item in plugin_opts.split(";"):
            if "=" in item:
                key, value = item.split("=", 1)
                opts[key] = value
        if opts:
            proxy["plugin-opts"] = opts
    return proxy


def parse_vmess_uri(uri: str) -> dict:
    encoded = uri[len("vmess://") :]
    decoded = base64.b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8")
    data = json.loads(decoded)
    proxy = {
        "name": data.get("ps") or "vmess-node",
        "type": "vmess",
        "server": data["add"],
        "port": int(data["port"]),
        "uuid": data["id"],
        "alterId": int(data.get("aid", 0)),
        "cipher": data.get("scy", "auto"),
        "udp": True,
    }
    if data.get("net"):
        proxy["network"] = data["net"]
    if data.get("path"):
        proxy["ws-opts"] = {"path": data["path"]}
    if data.get("host"):
        proxy.setdefault("ws-opts", {})["headers"] = {"Host": data["host"]}
    if data.get("tls") == "tls":
        proxy["tls"] = True
    if data.get("sni"):
        proxy["servername"] = data["sni"]
    return proxy


def parse_vless_or_trojan_uri(uri: str, proxy_type: str) -> dict:
    parsed = urllib.parse.urlparse(uri)
    query = urllib.parse.parse_qs(parsed.query)
    proxy = {
        "name": urllib.parse.unquote(parsed.fragment) or f"{proxy_type}-node",
        "type": proxy_type,
        "server": parsed.hostname or "",
        "port": parsed.port or 0,
        "udp": True,
    }
    if proxy_type == "vless":
        proxy["uuid"] = urllib.parse.unquote(parsed.username or "")
        proxy["flow"] = query.get("flow", [""])[0] or None
    else:
        proxy["password"] = urllib.parse.unquote(parsed.username or "")
    network = query.get("type", [""])[0]
    if network:
        proxy["network"] = network
    servername = query.get("sni", [""])[0] or query.get("peer", [""])[0]
    if servername:
        proxy["servername"] = servername
    if query.get("security", [""])[0] == "tls" or servername:
        proxy["tls"] = True
    if query.get("allowInsecure", [""])[0] == "1" or query.get("insecure", [""])[0] == "1":
        proxy["skip-cert-verify"] = True
    fingerprint = query.get("fp", [""])[0]
    if fingerprint:
        proxy["client-fingerprint"] = fingerprint
    alpn = [value for value in query.get("alpn", [""])[0].split(",") if value]
    if alpn:
        proxy["alpn"] = alpn
    ech = query.get("ech", [""])[0]
    if ech:
        server_name, _, config = ech.partition("+")
        proxy["ech-opts"] = {"enable": True}
        if server_name:
            proxy["ech-opts"]["query-server-name"] = server_name
        if config and "://" not in config:
            proxy["ech-opts"]["config"] = config
    path = query.get("path", [""])[0]
    host = query.get("host", [""])[0]
    if network == "ws":
        proxy["ws-opts"] = {}
        if path:
            proxy["ws-opts"]["path"] = path
        if host:
            proxy["ws-opts"]["headers"] = {"Host": host}
    if network == "grpc":
        service_name = query.get("serviceName", [""])[0]
        if service_name:
            proxy["grpc-opts"] = {"grpc-service-name": service_name}
    if proxy.get("flow") is None:
        proxy.pop("flow", None)
    return proxy


def parse_hysteria2_uri(uri: str) -> dict:
    parsed = urllib.parse.urlparse(uri)
    query = urllib.parse.parse_qs(parsed.query)
    proxy = {
        "name": urllib.parse.unquote(parsed.fragment) or "hysteria2-node",
        "type": "hysteria2",
        "server": parsed.hostname or "",
        "port": parsed.port or 0,
        "password": urllib.parse.unquote(parsed.username or ""),
        "udp": True,
    }
    if query.get("sni", [""])[0]:
        proxy["sni"] = query["sni"][0]
    if query.get("insecure", [""])[0] == "1":
        proxy["skip-cert-verify"] = True
    if query.get("obfs", [""])[0]:
        proxy["obfs"] = query["obfs"][0]
    if query.get("obfs-password", [""])[0]:
        proxy["obfs-password"] = query["obfs-password"][0]
    return proxy


def parse_uri_subscription(decoded_text: str) -> list[dict]:
    proxies = []
    for line in decoded_text.splitlines():
        uri = line.strip()
        if not uri or "://" not in uri or uri.startswith("STATUS="):
            continue
        if uri.startswith("ss://"):
            proxies.append(parse_ss_uri(uri))
        elif uri.startswith("vmess://"):
            proxies.append(parse_vmess_uri(uri))
        elif uri.startswith("vless://"):
            proxies.append(parse_vless_or_trojan_uri(uri, "vless"))
        elif uri.startswith("trojan://"):
            proxies.append(parse_vless_or_trojan_uri(uri, "trojan"))
        elif uri.startswith("hysteria2://"):
            proxies.append(parse_hysteria2_uri(uri))
    return proxies


def yaml_scalar(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def yaml_lines(value: object, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(yaml_lines(item, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {yaml_scalar(item)}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                lines.append(f"{prefix}-")
                lines.extend(yaml_lines(item, indent + 2))
            elif isinstance(item, list):
                lines.append(f"{prefix}-")
                lines.extend(yaml_lines(item, indent + 2))
            else:
                lines.append(f"{prefix}- {yaml_scalar(item)}")
        return lines
    return [f"{prefix}{yaml_scalar(value)}"]


def build_generated_config(proxies: list[dict]) -> str:
    names = [proxy["name"] for proxy in proxies]
    config = {
        "port": 17890,
        "socks-port": 17891,
        "redir-port": 0,
        "mixed-port": 17893,
        "allow-lan": False,
        "external-controller": "127.0.0.1:19090",
        "secret": DEFAULT_SECRET,
        "mode": "rule",
        "proxies": proxies,
        "proxy-groups": [
            {
                "name": "Auto",
                "type": "select",
                "proxies": names,
            }
        ],
        "rules": ["MATCH,Auto"],
    }
    return "\n".join(yaml_lines(config)) + "\n"


def build_generated_config_from_clash_yaml(config_text: str) -> str:
    proxies_block, names = extract_clash_proxies_block(config_text)
    config_lines = [
        f'port: 17890',
        f'socks-port: 17891',
        f'redir-port: 0',
        f'mixed-port: 17893',
        f'allow-lan: false',
        f'external-controller: "127.0.0.1:19090"',
        f'secret: "{DEFAULT_SECRET}"',
        f'mode: "rule"',
        *proxies_block,
        "proxy-groups:",
        "  -",
        '    name: "Auto"',
        '    type: "select"',
        "    proxies:",
        *[f"      - {yaml_scalar(name)}" for name in names],
        "rules:",
        '  - "MATCH,Auto"',
    ]
    return "\n".join(config_lines) + "\n"


def prepare_config_text(sub_url: str) -> tuple[str, str]:
    raw_text = fetch_url_bytes(sub_url).decode("utf-8", errors="replace")
    if "proxies:" in raw_text or "proxy-providers:" in raw_text:
        return patch_config(raw_text), "clash"

    decoded = maybe_decode_base64_text(raw_text)
    if decoded and "://" in decoded:
        proxies = parse_uri_subscription(decoded)
        if proxies:
            return build_generated_config(proxies), "shadowrocket"

    raise RuntimeError("Unsupported subscription format: expected Clash/Mihomo YAML or Shadowrocket URI subscription")


def pick_group(proxies: dict) -> tuple[str, list[str]]:
    if GROUP and GROUP in proxies and proxies[GROUP].get("all"):
        nodes = proxies[GROUP].get("all", [])
        return GROUP, nodes

    cands = []
    for name, v in proxies.items():
        if v.get("type") in ("Selector", "URLTest", "Fallback", "LoadBalance"):
            real = []
            for n in v.get("all", []):
                if n not in proxies:
                    continue
                t = proxies[n].get("type")
                if t in ("Selector", "URLTest", "Fallback", "LoadBalance", "Direct", "Reject"):
                    continue
                real.append(n)
            cands.append((len(real), name, real))
    cands.sort(reverse=True)
    if not cands or not cands[0][2]:
        raise RuntimeError("No testable proxy group found")
    return cands[0][1], cands[0][2]


def render_html_report(group: str, tested_at: str, subscription_url: str, results: list[dict]) -> str:
    rows = []
    for index, item in enumerate(results, 1):
        status = "成功" if item["status"] == "ok" else "失败"
        speed = f"{item['mbps']:.2f} Mbps" if item["mbps"] is not None else "-"
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{html.escape(item['node'])}</td>"
            f"<td class=\"{'ok' if item['status'] == 'ok' else 'fail'}\">{status}</td>"
            f"<td>{speed}</td>"
            "</tr>"
        )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Speedia 测速结果</title>
  <style>
    body {{
      margin: 0;
      background: #f4f7fb;
      color: #1b2430;
      font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .wrap {{
      max-width: 1080px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
    }}
    .meta {{
      margin: 0 0 20px;
      color: #5b6878;
    }}
    .card {{
      overflow: hidden;
      border: 1px solid #dce5ef;
      border-radius: 14px;
      background: #fff;
      box-shadow: 0 12px 32px rgba(16, 24, 40, 0.08);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid #e8eef5;
      text-align: left;
    }}
    th {{
      background: #f8fbff;
      font-weight: 600;
    }}
    tr:last-child td {{
      border-bottom: 0;
    }}
    .ok {{
      color: #067647;
      font-weight: 600;
    }}
    .fail {{
      color: #b42318;
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Speedia 测速结果</h1>
    <p class="meta">测试时间：{html.escape(tested_at)} · 节点数：{len(results)}</p>
    <p class="meta">订阅链接：{html.escape(subscription_url)}</p>
    <div class="card">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>节点</th>
            <th>状态</th>
            <th>速度</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows)}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""


def parse_curl_failure_reason(returncode: int, stdout: str, stderr: str) -> str:
    code = stdout.strip()
    error_text = stderr.lower()
    if returncode == 28 or "timed out" in error_text:
        return "timeout"
    if returncode == 35 or "ssl_connect" in error_text or "tls" in error_text:
        return "tls_error"
    if code.isdigit() and code != "000":
        return f"http_{code}"
    if returncode:
        return f"curl_{returncode}"
    return "fail"


def open_report(path: Path) -> bool:
    return webbrowser.open(path.resolve().as_uri())


def get_managed_version_dir(version: str) -> Path:
    return get_managed_install_root() / version


def install_binary_to(destination: Path, version: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    install_root = get_managed_install_root()
    version_dir = get_managed_version_dir(version)
    tmp_archive = install_root / "speedia.tar.gz.tmp"
    tmp_extract_dir = install_root / f".extract-{version}"
    shutil.rmtree(tmp_extract_dir, ignore_errors=True)
    version_dir.parent.mkdir(parents=True, exist_ok=True)
    download(get_release_asset_url(), tmp_archive)
    tmp_extract_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["tar", "-xzf", str(tmp_archive), "-C", str(tmp_extract_dir)], check=True)
    extracted_entry = next(tmp_extract_dir.iterdir())
    if version_dir.exists():
        shutil.rmtree(version_dir)
    extracted_entry.replace(version_dir)
    tmp_archive.unlink(missing_ok=True)
    shutil.rmtree(tmp_extract_dir, ignore_errors=True)
    if destination.exists() or destination.is_symlink():
        destination.unlink()
    destination.symlink_to(version_dir / "speedia")


def get_update_target_path() -> Path:
    managed_launcher = get_managed_launcher_path()
    if managed_launcher.exists() or managed_launcher.is_symlink():
        return managed_launcher
    raise RuntimeError("Managed install not found. Please install via install.sh first.")


def get_latest_release_version() -> str:
    response = requests.get(get_latest_release_api_url(), timeout=10)
    response.raise_for_status()
    return parse_latest_version_tag(response.json()["tag_name"])


def run_update() -> None:
    current_version = get_display_version()
    latest_version = get_latest_release_version()
    if latest_version == current_version:
        print(f"[done] speedia is already up to date ({current_version})")
        return
    print(f"[info] Updating speedia {current_version} -> {latest_version}")
    target = get_update_target_path()
    install_binary_to(target, latest_version)
    print(f"[done] Updated speedia to {latest_version}")


def run_uninstall() -> None:
    print("[info] Uninstalling speedia")
    launcher = get_managed_launcher_path()
    if launcher.exists() or launcher.is_symlink():
        launcher.unlink()
    install_root = get_managed_install_root()
    if install_root.exists():
        shutil.rmtree(install_root)
    print("[done] Uninstalled speedia")


def main() -> None:
    args = parse_args()
    if args.command == "update":
        run_update()
        return
    if args.command == "uninstall":
        run_uninstall()
        return

    sub_url = args.sub_url
    workdir = Path(tempfile.mkdtemp(prefix="mihomo-speedtest-"))
    cfg_path = workdir / "config.yaml"
    print(f"[info] Workdir: {workdir}")

    config_text, source_type = prepare_config_text(sub_url)
    cfg_path.write_text(config_text, encoding="utf-8")
    print(f"[info] Subscription type: {source_type}")

    mihomo_bin = get_mihomo_bin()
    mihomo_stderr_path = workdir / "mihomo.stderr.log"
    mihomo_stderr = mihomo_stderr_path.open("wb")
    proc = subprocess.Popen(
        [str(mihomo_bin), "-d", str(workdir), "-f", str(cfg_path)],
        stdout=subprocess.DEVNULL,
        stderr=mihomo_stderr,
    )

    try:
        headers = {"Authorization": f"Bearer {DEFAULT_SECRET}"}
        print("[info] Starting Mihomo")
        for _ in range(40):
            try:
                if requests.get(f"{API}/version", headers=headers, timeout=1).ok:
                    print("[info] Mihomo API ready")
                    break
            except Exception:
                pass
            time.sleep(0.4)
        else:
            stderr_text = mihomo_stderr_path.read_text(encoding="utf-8", errors="replace").strip()
            detail = f": {stderr_text}" if stderr_text else ""
            raise RuntimeError(f"Mihomo API not ready{detail}")

        proxies = requests.get(f"{API}/proxies", headers=headers, timeout=10).json()["proxies"]
        group, nodes = pick_group(proxies)
        nodes = nodes[:LIMIT]
        print(f"[info] Testing {len(nodes)} nodes")

        results = []
        for i, node in enumerate(nodes, 1):
            requests.put(
                f"{API}/proxies/{urllib.parse.quote(group, safe='')}",
                headers=headers,
                json={"name": node},
                timeout=8,
            )
            time.sleep(0.5)
            cmd = [
                "curl",
                "-L",
                "-o",
                "/dev/null",
                "-s",
                "-w",
                "%{http_code} %{speed_download}",
                "--proxy",
                HTTP_PROXY,
                "--max-time",
                str(MAX_TIME),
                TEST_URL,
            ]
            try:
                cp = subprocess.run(cmd, capture_output=True, text=True, timeout=MAX_TIME + 2)
                parts = cp.stdout.strip().split()
                http_code = parts[0] if parts else "000"
                speed_text = parts[1] if len(parts) > 1 else ""
                if cp.returncode == 0 and speed_text and http_code.startswith(("2", "3")):
                    bps = float(speed_text)
                    mbps = round(bps * 8 / 1_000_000, 2)
                    results.append({"node": node, "mbps": mbps, "status": "ok"})
                    print(f"[{i}/{len(nodes)}] {node}  {mbps:.2f} Mbps")
                else:
                    reason = parse_curl_failure_reason(cp.returncode, http_code, cp.stderr)
                    results.append({"node": node, "mbps": None, "status": "fail", "reason": reason})
                    print(f"[{i}/{len(nodes)}] {node}  FAIL {reason}")
            except Exception:
                results.append({"node": node, "mbps": None, "status": "fail", "reason": "exception"})
                print(f"[{i}/{len(nodes)}] {node}  FAIL exception")

        tested_at = time.strftime("%Y-%m-%d %H:%M:%S")
        out = {
            "group": group,
            "tested_count": len(nodes),
            "tested_at": tested_at,
            "subscription_url": sub_url,
            "results": results,
        }
        cwd = Path.cwd()
        out_path = cwd / "speed_results.json"
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        html_path = cwd / "speed_results.html"
        html_path.write_text(render_html_report(group, tested_at, sub_url, results), encoding="utf-8")
        print(f"[done] Saved: {out_path}")
        print(f"[done] Saved: {html_path}")
        if open_report(html_path):
            print(f"[done] Opened: {html_path}")
    finally:
        mihomo_stderr.close()
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


if __name__ == "__main__":
    main()
