import tempfile
import unittest
from pathlib import Path
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
            config_text, source_type = speedia.prepare_config_text("https://example.com/sub")

        self.assertEqual(source_type, "clash")
        self.assertIn("name: Node A", config_text)
        self.assertIn('secret: "speedia"', config_text)
        self.assertIn('rules:', config_text)
        self.assertIn('- "MATCH,Auto"', config_text)
        self.assertNotIn("GEOIP,CN,DIRECT", config_text)

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


class ReportTests(unittest.TestCase):
    def test_html_report_hides_group_from_meta(self) -> None:
        html = speedia.render_html_report(
            "🤖 OpenAi",
            "2026-04-08 12:57:57",
            "https://example.com/sub",
            [{"node": "节点A", "mbps": 12.34, "status": "ok"}],
        )

        self.assertNotIn("策略组：", html)
        self.assertNotIn("🤖 OpenAi", html)
        self.assertIn("测试时间：2026-04-08 12:57:57", html)
        self.assertIn("节点数：1", html)
        self.assertIn("https://example.com/sub", html)

    def test_open_report_uses_browser_with_file_uri(self) -> None:
        path = Path("/tmp/speed_results.html")
        with patch("speedia.webbrowser.open", return_value=True) as mock_open:
            result = speedia.open_report(path)

        self.assertEqual(result, True)
        mock_open.assert_called_once_with(path.resolve().as_uri())


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
