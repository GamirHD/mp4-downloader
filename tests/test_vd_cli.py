from __future__ import annotations

import argparse
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest import mock

import browser_login
import cookie_input
import page_extractor
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
            {
                "download_dir": str(folder),
                "use_download_archive": True,
                "cookies_from_browser": None,
                "cookies_from_clipboard": False,
            },
        )

    def test_settings_ignore_non_string_download_dir(self) -> None:
        vd_cli.save_settings({"download_dir": 123, "use_download_archive": True})

        settings = vd_cli.load_settings()

        self.assertEqual(settings["download_dir"], str(vd_cli.default_download_dir()))
        self.assertTrue(settings["use_download_archive"])

    def test_settings_parse_common_boolean_string_values(self) -> None:
        vd_cli.save_settings({"download_dir": str(vd_cli.default_download_dir()), "use_download_archive": "false"})

        self.assertFalse(vd_cli.load_settings()["use_download_archive"])

        vd_cli.save_settings({"download_dir": str(vd_cli.default_download_dir()), "use_download_archive": "true"})

        self.assertTrue(vd_cli.load_settings()["use_download_archive"])

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

    def test_version_flag_prints_package_version(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output):
            with self.assertRaises(SystemExit) as context:
                vd_cli.main(["--version"])

        self.assertEqual(context.exception.code, 0)
        self.assertIn(vd_cli.__version__, output.getvalue())

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

    def test_format_history_timestamp_returns_local_readable_string(self) -> None:
        value = "2026-07-13T12:34:56+00:00"
        expected = datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
        self.assertEqual(vd_cli.format_history_timestamp(value), expected)

    def test_dpapi_error_points_to_cookie_file(self) -> None:
        message = vd_cli.friendly_error("ERROR: Failed to decrypt with DPAPI. See https://github.com/yt-dlp/yt-dlp/issues/10927")
        self.assertIn("cookies.txt", message)
        self.assertNotIn("DRM", message)

    def test_cookie_error_points_to_cli_cookie_controls(self) -> None:
        message = vd_cli.friendly_error("Sign in to confirm you're not a bot. Use cookies.")

        self.assertIn("--cookies-from-browser", message)
        self.assertNotIn("GUI", message)

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

    def test_extract_urls_from_text_ignores_non_url_words(self) -> None:
        urls = vd_cli.extract_urls_from_text(
            "please download this https://example.test/1 and not these words"
        )

        self.assertEqual(urls, ["https://example.test/1"])

    def test_extract_urls_from_text_accepts_links_without_scheme(self) -> None:
        urls = vd_cli.extract_urls_from_text(
            "youtube.com/watch?v=abc www.example.test/video <youtu.be/xyz>."
        )

        self.assertEqual(
            urls,
            [
                "https://youtube.com/watch?v=abc",
                "https://www.example.test/video",
                "https://youtu.be/xyz",
            ],
        )

    def test_extract_urls_from_text_ignores_email_addresses(self) -> None:
        urls = vd_cli.extract_urls_from_text("mail test@example.com and use example.test/video")

        self.assertEqual(urls, ["https://example.test/video"])

    def test_extract_urls_from_text_trims_markdown_link_suffixes(self) -> None:
        urls = vd_cli.extract_urls_from_text(
            "[one](https://example.test/1), (https://example.test/2)"
        )

        self.assertEqual(
            urls,
            [
                "https://example.test/1",
                "https://example.test/2",
            ],
        )

    def test_extract_urls_from_text_keeps_balanced_url_brackets(self) -> None:
        urls = vd_cli.extract_urls_from_text(
            "https://example.test/watch(foo) https://example.test/list[bar] https://example.test/data{baz}"
        )

        self.assertEqual(
            urls,
            [
                "https://example.test/watch(foo)",
                "https://example.test/list[bar]",
                "https://example.test/data{baz}",
            ],
        )

    def test_normalize_url_args_splits_quoted_link_blocks(self) -> None:
        urls = vd_cli.normalize_url_args(
            [
                "https://example.test/1\nhttps://example.test/2,",
                "<https://example.test/3>",
                "https://example.test/1",
            ]
        )

        self.assertEqual(
            urls,
            [
                "https://example.test/1",
                "https://example.test/2",
                "https://example.test/3",
            ],
        )

    def test_main_explains_when_arguments_contain_no_urls(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output):
            result = vd_cli.main(["not-a-link"])

        self.assertEqual(result, 2)
        self.assertIn(vd_cli.no_urls_found_message(), output.getvalue())


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

    def test_no_archive_flag_can_override_saved_default_on(self) -> None:
        folder = Path(self.temp_dir.name) / "Downloads"
        vd_cli.save_settings({"download_dir": str(folder), "use_download_archive": True})

        with mock.patch.object(vd_cli, "choose_quality", return_value="best"):
            with mock.patch.object(vd_cli, "download", return_value={"title": "One"}) as download_mock:
                self.assertEqual(vd_cli.main(["https://example.test/1", "--no-archive"]), 0)

        self.assertFalse(download_mock.call_args.kwargs["use_download_archive"])


    def test_saved_browser_login_is_kept_and_invalid_values_are_ignored(self) -> None:
        folder = str(Path(self.temp_dir.name))
        vd_cli.save_settings({"download_dir": folder, "cookies_from_browser": "firefox"})
        self.assertEqual(vd_cli.load_settings()["cookies_from_browser"], "firefox")

        vd_cli.save_settings({"download_dir": folder, "cookies_from_browser": "netscape"})
        self.assertIsNone(vd_cli.load_settings()["cookies_from_browser"])

    def test_cookie_file_and_referer_options(self) -> None:
        options = vd_cli.build_ydl_options(
            "best",
            Path(self.temp_dir.name),
            cookie_file="cookies.txt",
            referer="https://ga.gg/premium-kurse/kurs/",
        )

        self.assertTrue(options["cookiefile"].endswith("cookies.txt"))
        self.assertEqual(options["http_headers"]["Referer"], "https://ga.gg/premium-kurse/kurs/")
        self.assertEqual(options["http_headers"]["Origin"], "https://ga.gg")

    def test_only_unsupported_pages_trigger_embedded_search(self) -> None:
        self.assertTrue(vd_cli.should_try_embedded_media("ERROR: Unsupported URL: https://ga.gg/x"))
        self.assertFalse(vd_cli.should_try_embedded_media("ERROR: This video is DRM protected"))
        self.assertFalse(vd_cli.should_try_embedded_media("ERROR: HTTP Error 404"))

    def test_embedded_media_options_use_page_title_and_referer(self) -> None:
        base = vd_cli.build_ydl_options("best", Path(self.temp_dir.name))
        media = vd_cli.EmbeddedMedia(
            page_url="https://ga.gg/premium-kurse/a/b/",
            title="Xioh Midlane Masterclass 100%",
            media_urls=["https://cdn.example/master.m3u8"],
        )

        options = vd_cli.embedded_media_options(base, media)

        self.assertEqual(options["http_headers"]["Referer"], "https://ga.gg/premium-kurse/a/b/")
        self.assertEqual(
            Path(options["outtmpl"]).name, "Xioh Midlane Masterclass 100%%.%(ext)s"
        )
        self.assertNotIn("http_headers", base)

    def test_embedded_media_options_accept_outtmpl_rewritten_by_yt_dlp(self) -> None:
        base = vd_cli.build_ydl_options("best", Path(self.temp_dir.name))
        base["outtmpl"] = {"default": base["outtmpl"]}
        media = vd_cli.EmbeddedMedia(page_url="https://ga.gg/a/", title="Kurs", media_urls=["https://c/m.m3u8"])

        options = vd_cli.embedded_media_options(base, media)

        self.assertEqual(Path(options["outtmpl"]), Path(self.temp_dir.name) / "Kurs.%(ext)s")


class PageExtractorTests(unittest.TestCase):
    PAGE = "https://ga.gg/premium-kurse/kurs/video/"

    def test_finds_master_playlist_before_variants_and_skips_segments(self) -> None:
        html = """
        <html><head><meta property="og:title" content="Xioh Midlane Masterclass"></head>
        <script>var cfg = {"hls":"https:\\/\\/cdn.example.com\\/v\\/abc\\/720p.m3u8?token=1\\u00262",
        "master":"https://cdn.example.com/v/abc/master.m3u8?token=1&amp;x=2"};</script>
        <a href="https://cdn.example.com/v/abc/seg-20-v1-a1.ts">x</a>
        </html>
        """
        urls = page_extractor.find_media_in_html(html, self.PAGE)

        self.assertEqual(urls[0], "https://cdn.example.com/v/abc/master.m3u8?token=1&x=2")
        self.assertIn("https://cdn.example.com/v/abc/720p.m3u8?token=1&2", urls)
        self.assertEqual(page_extractor.extract_page_title(html), "Xioh Midlane Masterclass")

    def test_finds_known_player_iframes_and_relative_video_sources(self) -> None:
        html = """
        <iframe src="//player.vimeo.com/video/123?h=abc"></iframe>
        <iframe src="https://ads.example.com/banner"></iframe>
        <video><source src="/media/intro.mp4"></video>
        """
        urls = page_extractor.find_media_in_html(html, self.PAGE)

        self.assertEqual(
            urls,
            ["https://ga.gg/media/intro.mp4", "https://player.vimeo.com/video/123?h=abc"],
        )

    def test_title_drops_site_name_suffix(self) -> None:
        self.assertEqual(page_extractor.clean_title("Xioh Midlane Masterclass | GA.GG"), "Xioh Midlane Masterclass")
        self.assertEqual(page_extractor.clean_title("Nur ein Titel"), "Nur ein Titel")

    def test_segment_files_are_not_media_candidates(self) -> None:
        self.assertFalse(page_extractor.is_media_url("https://cdn.example/seg-20-v1-a1.mp4"))
        self.assertTrue(page_extractor.is_media_url("https://cdn.example/index.m3u8?t=1"))

    def test_browser_only_gets_cookies_of_the_page_site(self) -> None:
        from http.cookiejar import Cookie

        def cookie(domain: str) -> Cookie:
            return Cookie(0, "session", "v", None, False, domain, True, True, "/", True,
                          True, None, False, None, None, {"HttpOnly": None})

        jar = [cookie(".ga.gg"), cookie("www.ga.gg"), cookie(".google.com")]
        cookies = page_extractor._playwright_cookies(jar, self.PAGE)

        self.assertEqual([item["domain"] for item in cookies], [".ga.gg", "www.ga.gg"])
        self.assertTrue(cookies[0]["httpOnly"])


class DownloadFallbackTests(unittest.TestCase):
    def test_unsupported_page_downloads_embedded_stream_with_referer(self) -> None:
        if vd_cli.yt_dlp is None:
            self.skipTest("yt-dlp nicht installiert")
        calls: list[tuple[str, dict]] = []

        class FakeYDL:
            def __init__(self, options):
                self.options = options
                self.cookiejar = []

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def extract_info(self, url, download=True):
                calls.append((url, self.options))
                if url.endswith("/video/"):
                    raise vd_cli.yt_dlp.utils.DownloadError("ERROR: Unsupported URL: " + url)
                return {"title": "master", "id": "master"}

        media = vd_cli.EmbeddedMedia(
            page_url="https://ga.gg/kurs/video/",
            title="Kurs Video",
            media_urls=["https://cdn.example/master.m3u8"],
        )
        options = vd_cli.build_ydl_options("best", Path(tempfile.gettempdir()))
        with mock.patch.object(vd_cli.yt_dlp, "YoutubeDL", FakeYDL), mock.patch.object(
            vd_cli, "find_embedded_media", return_value=media
        ):
            info = vd_cli.download_url("https://ga.gg/kurs/video/", options, log=lambda _text: None)

        self.assertEqual(info["title"], "Kurs Video")
        self.assertEqual(calls[1][0], "https://cdn.example/master.m3u8")
        self.assertEqual(calls[1][1]["http_headers"]["Referer"], "https://ga.gg/kurs/video/")

    def test_no_embedded_video_gives_clear_error(self) -> None:
        if vd_cli.yt_dlp is None:
            self.skipTest("yt-dlp nicht installiert")

        class FakeYDL:
            def __init__(self, options):
                self.cookiejar = []

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def extract_info(self, url, download=True):
                raise vd_cli.yt_dlp.utils.DownloadError("ERROR: Unsupported URL: " + url)

        options = vd_cli.build_ydl_options("best", Path(tempfile.gettempdir()))
        with mock.patch.object(vd_cli.yt_dlp, "YoutubeDL", FakeYDL), mock.patch.object(
            vd_cli, "find_embedded_media", return_value=None
        ):
            with self.assertRaises(RuntimeError) as ctx:
                vd_cli.download_url("https://ga.gg/kurs/video/", options, log=lambda _text: None)

        self.assertIn("Kein eingebettetes Video", vd_cli.friendly_error(str(ctx.exception)))


class CookieInputTests(unittest.TestCase):
    URL = "https://ga.gg/premium-kurse/kurs/video/"

    def test_netscape_text_is_kept_including_httponly_lines(self) -> None:
        text = (
            "# Netscape HTTP Cookie File\n# comment\n\n"
            "ga.gg\tFALSE\t/\tTRUE\t0\tPHPSESSID\tabc\n"
            "#HttpOnly_ga.gg\tFALSE\t/\tTRUE\t1794649663\twordpress_logged_in_x\tuser%7C1\n"
        )
        content, count = cookie_input.cookies_text_to_netscape(text, self.URL)

        self.assertEqual(count, 2)
        self.assertTrue(content.startswith("# Netscape HTTP Cookie File"))
        self.assertIn("#HttpOnly_ga.gg", content)

    def test_cookie_header_is_converted_for_the_link_domain(self) -> None:
        content, count = cookie_input.cookies_text_to_netscape(
            "cookie: PHPSESSID=abc; wordpress_logged_in_x=user%7C1==; empty=", "https://www.ga.gg/x/"
        )

        self.assertEqual(count, 3)
        self.assertIn(".ga.gg\tTRUE\t/\tFALSE\t0\twordpress_logged_in_x\tuser%7C1==", content)

    def test_random_clipboard_text_is_rejected(self) -> None:
        for text in ("", "   ", "https://ga.gg/premium-kurse/", "hallo welt"):
            with self.assertRaises(cookie_input.CookieInputError):
                cookie_input.cookies_text_to_netscape(text, self.URL)

    def test_temporary_cookie_file_is_deleted_even_on_error(self) -> None:
        with self.assertRaises(RuntimeError):
            with cookie_input.temporary_cookie_file("# Netscape HTTP Cookie File\n") as path:
                self.assertTrue(path.exists())
                remembered = path
                raise RuntimeError("download failed")
        self.assertFalse(remembered.exists())

    def test_cli_uses_clipboard_cookies_temporarily(self) -> None:
        clipboard = "ga.gg\tFALSE\t/\tTRUE\t0\tPHPSESSID\tabc\n"
        seen: dict[str, str] = {}

        def fake_download(url, quality_key, folder, **kwargs):
            path = Path(kwargs["cookie_file"])
            seen["path"] = str(path)
            seen["content"] = path.read_text(encoding="utf-8")
            return {"title": "Video"}

        with tempfile.TemporaryDirectory() as config, mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": config}):
            with mock.patch.object(vd_cli, "read_clipboard_text", return_value=clipboard), mock.patch.object(
                vd_cli, "clear_clipboard", return_value=True
            ) as clear_mock, mock.patch.object(vd_cli, "download", side_effect=fake_download):
                with redirect_stdout(io.StringIO()):
                    code = vd_cli.main([self.URL, "-q", "best", "--cookies-from-clipboard"])

        self.assertEqual(code, 0)
        self.assertIn("PHPSESSID", seen["content"])
        self.assertFalse(Path(seen["path"]).exists())
        clear_mock.assert_called_once()


class BrowserLoginTests(unittest.TestCase):
    def test_saved_cookies_are_filtered_by_site_path_and_expiry(self) -> None:
        cookies = [
            {"name": "login", "value": "a", "domain": "ga.gg", "path": "/", "expires": -1},
            {"name": "sub", "value": "b", "domain": ".ga.gg", "path": "/", "expires": 9999999999},
            {"name": "admin", "value": "c", "domain": "ga.gg", "path": "/wp-admin", "expires": -1},
            {"name": "old", "value": "d", "domain": "ga.gg", "path": "/", "expires": 1000},
            {"name": "other", "value": "e", "domain": ".google.com", "path": "/", "expires": -1},
        ]
        with tempfile.TemporaryDirectory() as temp:
            profile = Path(temp)
            browser_login._save_cookies(profile, cookies)

            self.assertTrue(browser_login.has_saved_login(profile))
            names = [c["name"] for c in browser_login.saved_cookies_for("https://ga.gg/premium-kurse/x/", profile)]
            self.assertEqual(names, ["login", "sub"])
            names = [c["name"] for c in browser_login.saved_cookies_for("https://www.ga.gg/x/", profile)]
            self.assertEqual(names, ["sub"])

            self.assertTrue(browser_login.delete_saved_login(profile))
            self.assertFalse(browser_login.has_saved_login(profile))

    def test_cookies_to_netscape_is_readable_by_yt_dlp_format(self) -> None:
        text = browser_login.cookies_to_netscape(
            [
                {"name": "a", "value": "1", "domain": ".ga.gg", "path": "/", "expires": 1900000000.5, "secure": True, "httpOnly": True},
                {"name": "b", "value": "2", "domain": "ga.gg", "path": "/", "expires": -1, "secure": False},
            ]
        )
        content, count = cookie_input.cookies_text_to_netscape(text, "https://ga.gg/")

        self.assertEqual(count, 2)
        self.assertIn("#HttpOnly_.ga.gg\tTRUE\t/\tTRUE\t1900000000\ta\t1", content)
        self.assertIn("ga.gg\tFALSE\t/\tFALSE\t0\tb\t2", content)

    def test_cli_uses_saved_login_automatically(self) -> None:
        seen: dict[str, str] = {}

        def fake_download(url, quality_key, folder, **kwargs):
            seen["content"] = Path(kwargs["cookie_file"]).read_text(encoding="utf-8")
            seen["path"] = kwargs["cookie_file"]
            return {"title": "Video"}

        with tempfile.TemporaryDirectory() as config, mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": config}):
            browser_login._save_cookies(
                _ensure_dir(vd_cli.login_profile_dir()),
                [{"name": "wordpress_logged_in_x", "value": "v", "domain": "ga.gg", "path": "/", "expires": -1}],
            )
            with mock.patch.object(vd_cli, "download", side_effect=fake_download), redirect_stdout(io.StringIO()):
                code = vd_cli.main(["https://ga.gg/premium-kurse/x/", "-q", "best"])

        self.assertEqual(code, 0)
        self.assertIn("wordpress_logged_in_x", seen["content"])
        self.assertFalse(Path(seen["path"]).exists())


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


if __name__ == "__main__":
    unittest.main()
