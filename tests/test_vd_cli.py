from __future__ import annotations

import argparse
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import vd_cli


class VdCliSharedStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.env_patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.temp_dir.name}, clear=False)
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)

    def test_settings_round_trip_preserves_archive_default(self) -> None:
        self.assertFalse(vd_cli.load_settings()["use_download_archive"])

        folder = Path(self.temp_dir.name) / "Downloads"
        vd_cli.save_settings({"download_dir": str(folder), "use_download_archive": True})

        self.assertEqual(
            vd_cli.load_settings(),
            {"download_dir": str(folder), "use_download_archive": True},
        )

    def test_history_deduplicates_newest_url_and_caps_entries(self) -> None:
        folder = Path(self.temp_dir.name) / "Downloads"
        vd_cli.add_history_entry("https://example.test/1", title="Old", quality_key="720p", folder=folder)
        vd_cli.add_history_entry("https://example.test/1", title="New", quality_key="mp3", folder=folder)

        for index in range(vd_cli.MAX_HISTORY_ENTRIES + 5):
            vd_cli.add_history_entry(
                f"https://example.test/{index + 2}",
                title=str(index),
                quality_key="best",
                folder=folder,
            )

        entries = vd_cli.load_history()
        self.assertEqual(len(entries), vd_cli.MAX_HISTORY_ENTRIES)
        self.assertEqual(len({entry["url"] for entry in entries}), vd_cli.MAX_HISTORY_ENTRIES)

    def test_history_ignores_entries_without_string_url(self) -> None:
        vd_cli.save_history(
            [
                {"url": " https://example.test/1 ", "title": " One ", "quality": "720p", "folder": " /tmp "},
                {"url": ""},
                {"url": ["https://example.test/2"], "title": "Two"},
                {"title": "Missing URL"},
            ]
        )

        entries = vd_cli.load_history()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["url"], "https://example.test/1")
        self.assertEqual(entries[0]["title"], "One")
        self.assertEqual(entries[0]["folder"], "/tmp")

    def test_history_command_rejects_zero_limit_in_parser(self) -> None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--limit", type=vd_cli.positive_int)

        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["--limit", "0"])

    def test_history_command_prints_requested_limit(self) -> None:
        folder = Path(self.temp_dir.name) / "Downloads"
        vd_cli.add_history_entry("https://example.test/1", title="One", quality_key="best", folder=folder)
        vd_cli.add_history_entry("https://example.test/2", title="Two", quality_key="best", folder=folder)

        output = io.StringIO()
        args = argparse.Namespace(clear=False, limit=1)
        with redirect_stdout(output):
            self.assertEqual(vd_cli.history_command(args), 0)

        text = output.getvalue()
        self.assertIn("1. Two", text)
        self.assertNotIn("2. One", text)

    def test_cookie_error_points_to_existing_cookie_controls(self) -> None:
        message = vd_cli.friendly_error("Sign in to confirm you're not a bot. Use cookies.")

        self.assertIn("--cookies-from-browser", message)
        self.assertIn("GUI", message)

    def test_extract_urls_from_text_splits_common_clipboard_separators(self) -> None:
        urls = vd_cli.extract_urls_from_text(
            " https://example.test/1\nhttps://example.test/2, https://example.test/3\t"
            "https://example.test/1 "
        )

        self.assertEqual(
            urls,
            [
                "https://example.test/1",
                "https://example.test/2",
                "https://example.test/3",
            ],
        )

    def test_extract_urls_from_text_trims_chat_link_wrappers(self) -> None:
        urls = vd_cli.extract_urls_from_text(
            "<https://example.test/1>, https://example.test/2. https://example.test/3!"
        )

        self.assertEqual(
            urls,
            [
                "https://example.test/1",
                "https://example.test/2",
                "https://example.test/3",
            ],
        )


class VdCliOptionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.env_patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.temp_dir.name}, clear=False)
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)

    def test_mp3_options_use_audio_postprocessor(self) -> None:
        options = vd_cli.build_ydl_options("mp3", Path(self.temp_dir.name))

        self.assertEqual(options["format"], "bestaudio/best")
        self.assertEqual(options["postprocessors"][0]["preferredcodec"], "mp3")

    def test_archive_and_browser_options_are_shared_by_cli_and_gui(self) -> None:
        options = vd_cli.build_ydl_options(
            "720p",
            Path(self.temp_dir.name),
            allow_playlist=True,
            cookies_from_browser="firefox",
            use_download_archive=True,
        )

        self.assertFalse(options["noplaylist"])
        self.assertEqual(options["cookiesfrombrowser"], ("firefox",))
        self.assertEqual(options["download_archive"], str(vd_cli.download_archive_path()))


if __name__ == "__main__":
    unittest.main()
