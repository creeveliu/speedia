import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import speedia


class GetMihomoBinTests(unittest.TestCase):
    def test_uses_cached_binary_without_redownloading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            cached_bin = cache_dir / "mihomo"
            cached_bin.write_text("bin", encoding="utf-8")

            with patch("speedia.shutil_which", return_value=""):
                with patch("speedia.get_cache_dir", return_value=cache_dir):
                    with patch("speedia.download") as mock_download:
                        result = speedia.get_mihomo_bin()

            self.assertEqual(result, cached_bin)
            mock_download.assert_not_called()

    def test_downloads_to_stable_gzip_path_before_unpacking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)

            def fake_gunzip(cmd: list[str], check: bool) -> None:
                self.assertEqual(cmd, ["gunzip", "-f", str(cache_dir / "mihomo.gz")])
                (cache_dir / "mihomo").write_text("bin", encoding="utf-8")

            with patch("speedia.shutil_which", return_value=""):
                with patch("speedia.get_cache_dir", return_value=cache_dir):
                    with patch("speedia.download") as mock_download:
                        with patch("speedia.subprocess.run", side_effect=fake_gunzip):
                            result = speedia.get_mihomo_bin()

            self.assertEqual(result, cache_dir / "mihomo")
            mock_download.assert_called_once()
            self.assertEqual(mock_download.call_args.args[1], cache_dir / "mihomo.gz")


class GeoIPTests(unittest.TestCase):
    def test_uses_cached_geoip_without_redownloading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            cached_geoip = cache_dir / "geoip.metadb"
            cached_geoip.write_text("geoip", encoding="utf-8")

            with patch("speedia.get_cache_dir", return_value=cache_dir):
                with patch("speedia.download") as mock_download:
                    result = speedia.get_geoip_db()

            self.assertEqual(result, cached_geoip)
            mock_download.assert_not_called()


class ConfigTests(unittest.TestCase):
    def test_patch_config_replaces_existing_secret_with_default(self) -> None:
        config = "secret: old-secret\nmixed-port: 7890\n"

        patched = speedia.patch_config(config)

        self.assertIn(f"secret: {speedia.DEFAULT_SECRET}\n", patched)
        self.assertNotIn("secret: old-secret\n", patched)

    def test_patch_config_adds_default_secret_when_missing(self) -> None:
        config = "mixed-port: 7890\n"

        patched = speedia.patch_config(config)

        self.assertIn(f"secret: {speedia.DEFAULT_SECRET}\n", patched)

    def test_prepare_config_text_builds_minimal_config_from_clash_yaml(self) -> None:
        raw = """
proxies:
  - name: Node A
    type: ss
    server: 1.1.1.1
    port: 443
    cipher: aes-128-gcm
    password: pass
rules:
  - GEOIP,CN,DIRECT
"""

        with patch("speedia.fetch_url_bytes", return_value=raw.encode("utf-8")):
            config_text, source_type, node_names = speedia.prepare_config_text("https://example.com/sub")

        self.assertEqual(source_type, "clash")
        self.assertEqual(node_names, ["Node A"])
        self.assertIn('port: 17890', config_text)
        self.assertIn('name: "Node A"', config_text)
        self.assertIn('secret: "speedia"', config_text)
        self.assertIn('name: "Auto"', config_text)
        self.assertIn('rules:', config_text)
        self.assertIn('MATCH,Auto', config_text)
        self.assertNotIn("GEOIP,CN,DIRECT", config_text)

    def test_prepare_config_text_drops_remote_clash_dependencies(self) -> None:
        raw = """
proxy-providers:
  provider-a:
    type: http
    url: https://example.com/provider.yaml
proxies:
  - name: Node A
    type: ss
    server: 1.1.1.1
    port: 443
    cipher: aes-128-gcm
    password: pass
rule-providers:
  reject:
    type: http
    url: https://example.com/reject.yaml
rules:
  - RULE-SET,reject,REJECT
"""

        config_text, source_type, node_names = speedia.prepare_config_text(raw)

        self.assertEqual(source_type, "clash")
        self.assertEqual(node_names, ["Node A"])
        self.assertNotIn("proxy-providers:", config_text)
        self.assertNotIn("rule-providers:", config_text)
        self.assertNotIn("https://example.com/provider.yaml", config_text)
        self.assertIn('MATCH,Auto', config_text)

    def test_prepare_config_text_accepts_direct_base64_subscription_content(self) -> None:
        raw = "dm1lc3M6Ly9leUpoWkdRaU9pSXhMakV1TVM0eElpd2ljRzl5ZENJNklqUTBNeUlzSW1sa0lqb2lkWFZwWkNJc0luQnpJam9pYm05a1pTSjk="

        config_text, source_type, node_names = speedia.prepare_config_text(raw)

        self.assertEqual(source_type, "shadowrocket")
        self.assertEqual(node_names, ["node"])
        self.assertIn('type: "vmess"', config_text)
        self.assertIn('name: "node"', config_text)

    def test_prepare_config_text_fetch_failure_suggests_pasting_subscription_content(self) -> None:
        with patch("speedia.fetch_url_bytes", side_effect=RuntimeError("403 Forbidden")):
            with patch.dict("speedia.os.environ", {"LANG": "zh_CN.UTF-8"}, clear=False):
                with self.assertRaises(RuntimeError) as ctx:
                    speedia.prepare_config_text("https://example.com/sub")

        self.assertIn("订阅链接访问失败", str(ctx.exception))
        self.assertIn("也可以直接传入订阅内容或 base64", str(ctx.exception))

    def test_build_generated_config_uses_proxy_names_for_auto_group(self) -> None:
        config_text = speedia.build_generated_config(
            [
                {"name": "A", "type": "ss", "server": "1.1.1.1", "port": 443, "cipher": "aes-128-gcm", "password": "x"},
                {"name": "B", "type": "ss", "server": "2.2.2.2", "port": 443, "cipher": "aes-128-gcm", "password": "y"},
            ]
        )

        self.assertIn('name: "Auto"', config_text)
        self.assertIn('- "A"', config_text)
        self.assertIn('- "B"', config_text)

    def test_parse_vless_preserves_tls_fingerprint_and_ech(self) -> None:
        uri = (
            "vless://uuid@example.com:443"
            "?security=tls&type=ws&sni=sm-1gn2.hoyoverse.online"
            "&fp=firefox"
            "&ech=cloudflare-ech.com%2Bhttps%3A%2F%2F223.5.5.5%2Fdns-query"
            "&path=%2F3021%2Findex%3Fed%3D4096"
            "&host=hk-sm.hoyoverse.online"
            "#hk"
        )

        proxy = speedia.parse_vless_or_trojan_uri(uri, "vless")

        self.assertEqual(proxy["client-fingerprint"], "firefox")
        self.assertEqual(proxy["ech-opts"]["enable"], True)
        self.assertEqual(proxy["ech-opts"]["query-server-name"], "cloudflare-ech.com")

    def test_parse_vless_preserves_skip_cert_verify(self) -> None:
        uri = "vless://uuid@example.com:443?security=tls&allowInsecure=1#hk"

        proxy = speedia.parse_vless_or_trojan_uri(uri, "vless")

        self.assertEqual(proxy["skip-cert-verify"], True)


class CliTests(unittest.TestCase):
    def test_parse_args_defaults_to_speedtest_url(self) -> None:
        args = speedia.parse_args(["https://example.com/sub"])
        self.assertEqual(args.command, "test")
        self.assertEqual(args.sub_url, "https://example.com/sub")

    def test_parse_args_supports_update(self) -> None:
        args = speedia.parse_args(["update"])
        self.assertEqual(args.command, "update")
        self.assertIsNone(args.sub_url)

    def test_parse_args_supports_uninstall(self) -> None:
        args = speedia.parse_args(["uninstall"])
        self.assertEqual(args.command, "uninstall")
        self.assertIsNone(args.sub_url)

    def test_get_release_asset_name_for_darwin_arm64(self) -> None:
        with patch("speedia.platform.system", return_value="Darwin"):
            with patch("speedia.platform.machine", return_value="arm64"):
                self.assertEqual(speedia.get_release_asset_name(), "speedia-darwin-arm64.tar.gz")

    def test_get_release_asset_name_for_linux_amd64(self) -> None:
        with patch("speedia.platform.system", return_value="Linux"):
            with patch("speedia.platform.machine", return_value="x86_64"):
                self.assertEqual(speedia.get_release_asset_name(), "speedia-linux-amd64.tar.gz")

    def test_get_display_version_uses_embedded_or_default(self) -> None:
        with patch.dict("speedia.os.environ", {"SPEEDIA_VERSION": "1.2.3"}, clear=False):
            self.assertEqual(speedia.get_display_version(), "1.2.3")

    def test_parse_latest_version_tag(self) -> None:
        self.assertEqual(speedia.parse_latest_version_tag("v1.2.3"), "1.2.3")

    def test_parse_release_version_from_url(self) -> None:
        url = "https://github.com/creeveliu/speedia/releases/tag/v1.2.3"
        self.assertEqual(speedia.parse_release_version_from_url(url), "1.2.3")

    def test_get_latest_release_version_prefers_release_page_redirect(self) -> None:
        with patch(
            "speedia.requests.get",
            return_value=SimpleNamespace(
                url="https://github.com/creeveliu/speedia/releases/tag/v1.2.3",
                raise_for_status=lambda: None,
            ),
        ) as mock_get:
            self.assertEqual(speedia.get_latest_release_version(), "1.2.3")
        self.assertEqual(mock_get.call_count, 1)


class ReportTests(unittest.TestCase):
    def test_html_report_shows_test_info(self) -> None:
        html = speedia.render_html_report(
            "2026-04-08 12:57:57",
            "https://example.com/sub",
            [{"node": "节点A", "mbps": 12.34, "status": "ok"}],
        )

        self.assertIn("测试时间：2026-04-08 12:57:57", html)
        self.assertIn("节点数：1", html)
        self.assertIn("https://example.com/sub", html)
        self.assertIn("订阅链接：", html)
        self.assertIn("toggleSubUrl", html)
        self.assertIn("分享截图", html)
        self.assertIn("已隐藏", html)
        self.assertIn("drawReportImage", html)
        self.assertNotIn("foreignObject", html)
        self.assertIn("/_client_open", html)
        self.assertIn("/_client_close", html)
        self.assertIn("sendBeacon", html)

    def test_open_report_uses_browser_with_file_uri(self) -> None:
        path = Path("/tmp/speed_results.html")
        with patch("speedia.start_report_server", return_value="http://127.0.0.1:8765/speed_results.html"):
            with patch("speedia.webbrowser.open", return_value=True) as mock_open:
                opened, url = speedia.open_report(path)

        self.assertEqual(opened, True)
        self.assertEqual(url, "http://127.0.0.1:8765/speed_results.html")
        mock_open.assert_called_once()
        self.assertIn("http://127.0.0.1:", mock_open.call_args.args[0])

    def test_get_report_dir_uses_system_temp_dir(self) -> None:
        with patch("speedia.tempfile.gettempdir", return_value="/tmp/test-root"):
            report_dir = speedia.get_report_dir()

        self.assertEqual(report_dir, Path("/tmp/test-root") / "speedia")

    def test_copy_image_to_clipboard_uses_osascript_on_macos(self) -> None:
        image_path = Path("/tmp/test.png")
        with patch("speedia.platform.system", return_value="Darwin"):
            with patch("speedia.subprocess.run") as mock_run:
                speedia.copy_image_to_clipboard(image_path)

        mock_run.assert_called_once()
        self.assertIn("osascript", mock_run.call_args.args[0][0])
        self.assertIn(str(image_path), " ".join(mock_run.call_args.args[0]))


class CurlResultTests(unittest.TestCase):
    def test_parse_failure_reason_from_ssl_error(self) -> None:
        reason = speedia.parse_curl_failure_reason(
            35,
            "",
            "curl: (35) LibreSSL SSL_connect: SSL_ERROR_SYSCALL in connection to speed.cloudflare.com:443",
        )
        self.assertEqual(reason, "tls_error")

    def test_parse_failure_reason_from_timeout(self) -> None:
        reason = speedia.parse_curl_failure_reason(
            28,
            "",
            "curl: (28) Connection timed out after 6002 milliseconds",
        )
        self.assertEqual(reason, "timeout")

    def test_parse_failure_reason_from_http_code(self) -> None:
        reason = speedia.parse_curl_failure_reason(0, "502", "")
        self.assertEqual(reason, "http_502")


if __name__ == "__main__":
    unittest.main()
