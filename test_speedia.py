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


class ReportTests(unittest.TestCase):
    def test_html_report_hides_group_from_meta(self) -> None:
        html = speedia.render_html_report(
            "🤖 OpenAi",
            "2026-04-08 12:57:57",
            [{"node": "节点A", "mbps": 12.34, "status": "ok"}],
        )

        self.assertNotIn("策略组：", html)
        self.assertNotIn("🤖 OpenAi", html)
        self.assertIn("测试时间：2026-04-08 12:57:57", html)
        self.assertIn("节点数：1", html)


if __name__ == "__main__":
    unittest.main()
