from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest import mock

import browser_login
import browsers
import page_extractor
import vd_cli


class ConfigTestCase(unittest.TestCase):
    """Every test gets its own empty settings folder."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        patcher = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.temp_dir.name, "APPDATA": self.temp_dir.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.folder = Path(self.temp_dir.name) / "Downloads"


class SettingsAndHistoryTests(ConfigTestCase):
    def test_settings_defaults_round_trip_and_ignore_old_keys(self) -> None:
        self.assertEqual(vd_cli.load_settings()["quality"], "1080p")

        vd_cli.save_settings({"download_dir": str(self.folder), "quality": "720p", "use_download_archive": True})

        self.assertEqual(vd_cli.load_settings(), {"download_dir": str(self.folder), "quality": "720p"})

    def test_settings_ignore_invalid_values(self) -> None:
        vd_cli.config_path().parent.mkdir(parents=True, exist_ok=True)
        vd_cli.config_path().write_text('{"download_dir": 123, "quality": "8k"}', encoding="utf-8")

        settings = vd_cli.load_settings()

        self.assertEqual(settings["download_dir"], str(vd_cli.default_download_dir()))
        self.assertEqual(settings["quality"], "1080p")

    def test_settings_command_changes_folder_and_quality(self) -> None:
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(vd_cli.main(["settings", "-f", str(self.folder), "-q", "mp3"]), 0)

        self.assertEqual(vd_cli.load_settings()["quality"], "mp3")
        self.assertTrue(self.folder.is_dir())
        self.assertIn("Nur Audio", output.getvalue())

    def test_history_deduplicates_newest_url_and_caps_entries(self) -> None:
        vd_cli.add_history_entry("https://example.test/1", title="Old", quality_key="720p", folder=self.folder)
        vd_cli.add_history_entry("https://example.test/1", title="New", quality_key="mp3", folder=self.folder)
        for index in range(vd_cli.MAX_HISTORY_ENTRIES + 5):
            vd_cli.add_history_entry(f"https://example.test/{index + 2}", title=str(index), quality_key="best", folder=self.folder)

        entries = vd_cli.load_history()
        self.assertEqual(len(entries), vd_cli.MAX_HISTORY_ENTRIES)
        self.assertEqual(len({entry["url"] for entry in entries}), vd_cli.MAX_HISTORY_ENTRIES)

    def test_history_ignores_entries_without_string_url(self) -> None:
        vd_cli.save_history([{"url": " https://example.test/1 ", "title": " One "}, {"url": ""}, {"title": "x"}])

        entries = vd_cli.load_history()
        self.assertEqual([(e["url"], e["title"]) for e in entries], [("https://example.test/1", "One")])

    def test_history_command_lists_and_clears(self) -> None:
        vd_cli.add_history_entry("https://example.test/1", title="One", quality_key="best", folder=self.folder)
        with redirect_stdout(io.StringIO()) as output:
            vd_cli.main(["history"])
        self.assertIn("One", output.getvalue())

        with redirect_stdout(io.StringIO()):
            vd_cli.main(["history", "--clear"])
        self.assertEqual(vd_cli.load_history(), [])

    def test_format_history_timestamp_returns_local_readable_string(self) -> None:
        value = "2026-07-13T12:34:56+00:00"
        expected = datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
        self.assertEqual(vd_cli.format_history_timestamp(value), expected)


class CommandLineTests(ConfigTestCase):
    def test_version_flag_prints_package_version(self) -> None:
        with redirect_stdout(io.StringIO()) as output, self.assertRaises(SystemExit) as context:
            vd_cli.main(["--version"])
        self.assertEqual(context.exception.code, 0)
        self.assertIn(vd_cli.__version__, output.getvalue())

    def test_without_links_shows_short_help_with_commands(self) -> None:
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(vd_cli.main([]), 2)
        self.assertIn("vd login", output.getvalue())
        self.assertNotIn("--debug", output.getvalue())

    def test_text_without_links_is_explained(self) -> None:
        with redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(vd_cli.main(["not-a-link"]), 2)
        self.assertIn(vd_cli.no_urls_found_message(), errors.getvalue())

    def test_download_uses_saved_quality_audio_flag_and_reports_file(self) -> None:
        vd_cli.save_settings({"download_dir": str(self.folder), "quality": "720p"})
        calls = []

        def fake_run(url, quality_key, folder, **kwargs):
            calls.append((quality_key, folder))
            return {"title": "Clip", "requested_downloads": [{"filepath": str(folder / "Clip.mp4")}]}

        with mock.patch.object(vd_cli, "run_download", side_effect=fake_run), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(vd_cli.main(["https://example.test/a"]), 0)
            self.assertEqual(vd_cli.main(["-a", "https://example.test/b"]), 0)

        self.assertEqual(calls, [("720p", self.folder), ("mp3", self.folder)])
        self.assertIn(f"Gespeichert: {self.folder / 'Clip.mp4'}", output.getvalue())
        self.assertEqual(vd_cli.load_history()[0]["title"], "Clip")

    def test_failed_download_shows_friendly_error(self) -> None:
        error = RuntimeError("ERROR: [generic] abc: Unable to download webpage: HTTP Error 404: Not Found")
        with mock.patch.object(vd_cli, "run_download", side_effect=error), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(vd_cli.main(["https://example.test/a"]), 1)
        self.assertIn("nicht gefunden (404)", errors.getvalue())
        self.assertNotIn("ERROR", errors.getvalue())

    def test_friendly_errors(self) -> None:
        self.assertIn("DRM", vd_cli.friendly_error("ERROR: This video is DRM protected"))
        self.assertIn("vd login", vd_cli.friendly_error("Sign in to confirm you're not a bot"))
        self.assertIn("ffmpeg", vd_cli.friendly_error("ERROR: ffmpeg not found"))


class LinkParsingTests(unittest.TestCase):
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


class OptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.gettempdir())

    def test_mp3_options_use_audio_postprocessor(self) -> None:
        options = vd_cli.build_ydl_options("mp3", self.folder)
        self.assertEqual(options["format"], "bestaudio/best")
        self.assertEqual(options["postprocessors"][0]["preferredcodec"], "mp3")

    def test_output_is_quiet_and_named_after_title(self) -> None:
        options = vd_cli.build_ydl_options("1080p", self.folder)
        self.assertTrue(options["noprogress"])
        self.assertIsInstance(options["logger"], vd_cli._SilentLogger)
        self.assertTrue(options["outtmpl"].endswith("%(title).200s.%(ext)s"))

    def test_quality_selectors_skip_huge_original_uploads(self) -> None:
        if vd_cli.yt_dlp is None:
            self.skipTest("yt-dlp nicht installiert")
        formats = [
            {"format_id": "original", "ext": "mp4", "height": 1080, "vcodec": "h264", "acodec": "aac", "url": "o", "tbr": 9000},
            {"format_id": "hd-1080p", "ext": "mp4", "height": 1080, "vcodec": "h264", "acodec": "aac", "url": "h", "tbr": 3000},
            {"format_id": "md-720p", "ext": "mp4", "height": 720, "vcodec": "h264", "acodec": "aac", "url": "m", "tbr": 1500},
        ]
        ydl = vd_cli.yt_dlp.YoutubeDL({"quiet": True})
        for key, expected in (("best", "hd-1080p"), ("1080p", "hd-1080p"), ("720p", "md-720p")):
            selector = ydl.build_format_selector(vd_cli.QUALITY_OPTIONS[key][1])
            picked = list(selector({"formats": sorted(formats, key=lambda f: f["tbr"]), "has_merged_format": True, "incomplete_formats": False}))
            self.assertEqual([f["format_id"] for f in picked], [expected], key)

    def test_cookie_file_and_referer_options(self) -> None:
        options = vd_cli.build_ydl_options("best", self.folder, cookie_file="cookies.txt", referer="https://example.com/kurs/")
        self.assertTrue(options["cookiefile"].endswith("cookies.txt"))
        self.assertEqual(options["http_headers"], {"Referer": "https://example.com/kurs/", "Origin": "https://example.com"})

    def test_only_unsupported_pages_trigger_embedded_search(self) -> None:
        self.assertTrue(vd_cli.should_try_embedded_media("ERROR: Unsupported URL: https://example.com/x"))
        self.assertFalse(vd_cli.should_try_embedded_media("ERROR: This video is DRM protected"))
        self.assertFalse(vd_cli.should_try_embedded_media("ERROR: HTTP Error 404"))

    def test_embedded_media_options_use_page_title_and_referer(self) -> None:
        base = vd_cli.build_ydl_options("best", self.folder)
        base["outtmpl"] = {"default": base["outtmpl"]}  # yt-dlp rewrites it like this
        media = vd_cli.EmbeddedMedia(page_url="https://example.com/a/", title="Kurs 100%", media_urls=["https://c/m.m3u8"])

        options = vd_cli.embedded_media_options(base, media)

        self.assertEqual(options["http_headers"]["Referer"], "https://example.com/a/")
        self.assertEqual(Path(options["outtmpl"]), self.folder / "Kurs 100%%.%(ext)s")

    def test_progress_line_formatting(self) -> None:
        self.assertEqual(vd_cli.format_size(1536 * 1024 * 1024), "1,5 GB")
        self.assertEqual(vd_cli.format_eta(3725), "1:02:05")
        self.assertEqual(vd_cli.format_eta(65), "1:05")

        stream = io.StringIO()
        progress = vd_cli.ConsoleProgress(stream)
        progress.hook({"status": "downloading", "filename": "a.mp4", "info_dict": {"title": "Clip"}, "downloaded_bytes": 5})
        progress.hook({"status": "finished", "filename": "a.mp4", "info_dict": {"title": "Clip"}, "total_bytes": 10})
        self.assertEqual(stream.getvalue(), "Lade: a\n")
        self.assertEqual(vd_cli.display_name("/x/Mein Video.f137.mp4.part"), "Mein Video")
        self.assertEqual(vd_cli.display_name("C:/x/Kurs 1.mp4"), "Kurs 1")

class PageExtractorTests(unittest.TestCase):
    PAGE = "https://example.com/kurse/kurs/video/"

    def test_finds_master_playlist_before_variants_and_skips_segments(self) -> None:
        html = """
        <html><head><meta property="og:title" content="Mein Kurs Video"></head>
        <script>var cfg = {"hls":"https:\\/\\/cdn.example.com\\/v\\/abc\\/720p.m3u8?token=1\\u00262",
        "master":"https://cdn.example.com/v/abc/master.m3u8?token=1&amp;x=2"};</script>
        <a href="https://cdn.example.com/v/abc/seg-20-v1-a1.ts">x</a>
        </html>
        """
        urls = page_extractor.find_media_in_html(html, self.PAGE)

        self.assertEqual(urls[0], "https://cdn.example.com/v/abc/master.m3u8?token=1&x=2")
        self.assertIn("https://cdn.example.com/v/abc/720p.m3u8?token=1&2", urls)
        self.assertEqual(page_extractor.extract_page_title(html), "Mein Kurs Video")

    def test_finds_known_player_iframes_and_relative_video_sources(self) -> None:
        html = """
        <iframe src="//player.vimeo.com/video/123?h=abc"></iframe>
        <iframe src="https://ads.example.com/banner"></iframe>
        <video><source src="/media/intro.mp4"></video>
        """
        urls = page_extractor.find_media_in_html(html, self.PAGE)

        self.assertEqual(
            urls,
            ["https://example.com/media/intro.mp4", "https://player.vimeo.com/video/123?h=abc"],
        )

    def test_title_drops_site_name_suffix(self) -> None:
        self.assertEqual(page_extractor.clean_title("Mein Kurs Video | Example"), "Mein Kurs Video")
        self.assertEqual(page_extractor.clean_title("Nur ein Titel"), "Nur ein Titel")

    def test_segment_files_are_not_media_candidates(self) -> None:
        self.assertFalse(page_extractor.is_media_url("https://cdn.example/seg-20-v1-a1.mp4"))
        self.assertTrue(page_extractor.is_media_url("https://cdn.example/index.m3u8?t=1"))

    def test_browser_only_gets_cookies_of_the_page_site(self) -> None:
        from http.cookiejar import Cookie

        def cookie(domain: str) -> Cookie:
            return Cookie(0, "session", "v", None, False, domain, True, True, "/", True,
                          True, None, False, None, None, {"HttpOnly": None})

        jar = [cookie(".example.com"), cookie("www.example.com"), cookie(".google.com")]
        cookies = page_extractor._playwright_cookies(jar, self.PAGE)

        self.assertEqual([item["domain"] for item in cookies], [".example.com", "www.example.com"])
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
            page_url="https://example.com/kurs/video/",
            title="Kurs Video",
            media_urls=["https://cdn.example/master.m3u8"],
        )
        options = vd_cli.build_ydl_options("best", Path(tempfile.gettempdir()))
        with mock.patch.object(vd_cli.yt_dlp, "YoutubeDL", FakeYDL), mock.patch.object(
            vd_cli, "find_embedded_media", return_value=media
        ):
            info = vd_cli.download_url("https://example.com/kurs/video/", options, log=lambda _text: None)

        self.assertEqual(info["title"], "Kurs Video")
        self.assertEqual(calls[1][0], "https://cdn.example/master.m3u8")
        self.assertEqual(calls[1][1]["http_headers"]["Referer"], "https://example.com/kurs/video/")

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
                vd_cli.download_url("https://example.com/kurs/video/", options, log=lambda _text: None)

        self.assertIn("Kein eingebettetes Video", vd_cli.friendly_error(str(ctx.exception)))



class LoginTests(ConfigTestCase):
    def save(self, *cookies: dict) -> None:
        browser_login._save_cookies(vd_cli.login_profile_dir(), list(cookies))

    def test_saved_cookies_are_filtered_by_site_path_and_expiry(self) -> None:
        self.save(
            {"name": "login", "value": "a", "domain": "example.com", "path": "/", "expires": -1},
            {"name": "sub", "value": "b", "domain": ".example.com", "path": "/", "expires": 9999999999},
            {"name": "admin", "value": "c", "domain": "example.com", "path": "/wp-admin", "expires": -1},
            {"name": "old", "value": "d", "domain": "example.com", "path": "/", "expires": 1000},
            {"name": "other", "value": "e", "domain": ".google.com", "path": "/", "expires": -1},
        )
        profile = vd_cli.login_profile_dir()
        self.assertEqual([c["name"] for c in browser_login.saved_cookies_for("https://example.com/kurse/x/", profile)], ["login", "sub"])
        self.assertEqual([c["name"] for c in browser_login.saved_cookies_for("https://www.example.com/x/", profile)], ["sub"])

    def test_logins_of_several_sites_are_kept_listed_and_removed_separately(self) -> None:
        self.save({"name": "s", "value": "1", "domain": "kurse.example.com", "path": "/"})
        self.save({"name": "t", "value": "2", "domain": ".vimeo.com", "path": "/"})
        self.save({"name": "s", "value": "new", "domain": "kurse.example.com", "path": "/"})
        profile = vd_cli.login_profile_dir()

        self.assertEqual(browser_login.saved_sites(profile), [("kurse.example.com", 1), ("vimeo.com", 1)])
        self.assertEqual(browser_login.saved_cookies_for("https://kurse.example.com/a", profile)[0]["value"], "new")

        with redirect_stdout(io.StringIO()) as output:
            vd_cli.main(["logout", "https://www.vimeo.com/123"])
            vd_cli.main(["login"])
        self.assertIn("Login für vimeo.com gelöscht", output.getvalue())
        self.assertIn("kurse.example.com", output.getvalue().split("gelöscht")[1])
        self.assertEqual(browser_login.saved_sites(profile), [("kurse.example.com", 1)])

    def test_cookies_to_netscape_and_temporary_file(self) -> None:
        text = browser_login.cookies_to_netscape(
            [{"name": "a", "value": "1", "domain": ".example.com", "path": "/", "expires": 1900000000.5, "secure": True, "httpOnly": True}]
        )
        self.assertIn("#HttpOnly_.example.com\tTRUE\t/\tTRUE\t1900000000\ta\t1", text)

        with self.assertRaises(RuntimeError):
            with browser_login.temporary_cookie_file(text) as path:
                remembered = path
                self.assertIn("a\t1", path.read_text(encoding="utf-8"))
                raise RuntimeError("download failed")
        self.assertFalse(remembered.exists())

    def test_login_might_help_skips_drm_and_tool_errors(self) -> None:
        self.assertTrue(vd_cli.login_might_help("ERROR: HTTP Error 403: Forbidden"))
        self.assertTrue(vd_cli.login_might_help("This video is only available for registered users"))
        self.assertTrue(vd_cli.login_might_help("Kein eingebettetes Video auf der Seite gefunden."))
        self.assertFalse(vd_cli.login_might_help("ERROR: This video is DRM protected"))
        self.assertFalse(vd_cli.login_might_help("ffmpeg not found"))
        self.assertFalse(vd_cli.login_might_help("HTTP Error 404: Not Found"))

    def test_saved_login_is_used_automatically_and_file_removed(self) -> None:
        self.save({"name": "wordpress_logged_in_x", "value": "v", "domain": "example.com", "path": "/"})
        seen = {}

        def fake_download_url(url, options, **kwargs):
            seen["path"] = options["cookiefile"]
            seen["content"] = Path(options["cookiefile"]).read_text(encoding="utf-8")
            return {"title": "Video"}

        with mock.patch.object(vd_cli, "download_url", side_effect=fake_download_url):
            vd_cli.run_download("https://example.com/kurse/x/", "best", self.folder, log=lambda _t: None)

        self.assertIn("wordpress_logged_in_x", seen["content"])
        self.assertFalse(Path(seen["path"]).exists())

    def test_login_is_offered_and_download_retried(self) -> None:
        calls = []

        def fake_download_url(url, options, **kwargs):
            calls.append(options.get("cookiefile"))
            if len(calls) == 1:
                raise RuntimeError("Kein eingebettetes Video auf der Seite gefunden.")
            return {"title": "Video"}

        def fake_login(url, profile_dir, **kwargs):
            browser_login._save_cookies(profile_dir, [{"name": "login", "value": "v", "domain": "example.com", "path": "/"}])
            return 1

        questions = []
        with mock.patch.object(vd_cli, "download_url", side_effect=fake_download_url), mock.patch.object(
            vd_cli, "interactive_login", side_effect=fake_login
        ):
            info = vd_cli.run_download(
                "https://example.com/kurse/x/", "best", self.folder, log=lambda _t: None,
                ask=lambda q: questions.append(q) or True,
            )

        self.assertEqual(info["title"], "Video")
        self.assertEqual(len(calls), 2)
        self.assertIsNone(calls[0])
        self.assertIsNotNone(calls[1])
        self.assertIn("example.com", questions[0])

    def test_no_login_prompt_for_drm_or_without_question_callback(self) -> None:
        with mock.patch.object(vd_cli, "download_url", side_effect=RuntimeError("This video is DRM protected")):
            with self.assertRaises(RuntimeError):
                vd_cli.run_download("https://example.com/x/", "best", self.folder, log=lambda _t: None, ask=lambda q: self.fail(q))

        with mock.patch.object(vd_cli, "download_url", side_effect=RuntimeError("HTTP Error 403: Forbidden")):
            with self.assertRaises(RuntimeError) as ctx:
                vd_cli.run_download("https://example.com/x/", "best", self.folder, log=lambda _t: None, ask=None)
        self.assertIn('vd login "https://example.com/x/"', str(ctx.exception))

    def test_explicit_cookie_file_disables_saved_login_and_prompt(self) -> None:
        self.save({"name": "login", "value": "v", "domain": "example.com", "path": "/"})
        with mock.patch.object(vd_cli, "download_url", side_effect=RuntimeError("HTTP Error 403")) as dl:
            with self.assertRaises(RuntimeError):
                vd_cli.run_download("https://example.com/x/", "best", self.folder, cookie_file="my.txt",
                                    log=lambda _t: None, ask=lambda q: self.fail(q))
        self.assertTrue(dl.call_args.args[1]["cookiefile"].endswith("my.txt"))


class BrowserChoiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def fake_exe(self, name: str) -> str:
        path = Path(self.temp.name) / name
        path.write_text("", encoding="utf-8")
        return str(path)

    def test_chromium_default_browser_comes_first(self) -> None:
        brave = self.fake_exe("brave.exe")
        choices = browsers.browser_choices(brave)
        self.assertEqual([c.name for c in choices], ["Brave", "Edge", "Chrome", "Chromium"])
        self.assertEqual(choices[0].launch_kwargs, {"executable_path": brave})
        self.assertEqual(choices[0].key, f"exe:{brave}")

    def test_firefox_or_missing_default_falls_back_to_edge(self) -> None:
        for default in (self.fake_exe("firefox.exe"), str(Path(self.temp.name) / "brave.exe.missing"), ""):
            self.assertEqual(browsers.browser_choices(default)[0].name, "Edge")

    def test_registry_command_is_parsed(self) -> None:
        self.assertEqual(
            browsers._first_token('"C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe" --single-argument %1'),
            "C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe",
        )

    def test_login_profile_is_renewed_when_default_browser_changed(self) -> None:
        profile = Path(self.temp.name) / "profile"
        profile.mkdir()
        (profile / browser_login.CHANNEL_FILE).write_text("msedge", encoding="utf-8")
        (profile / browser_login.COOKIES_FILE).write_text("[]", encoding="utf-8")
        (profile / "Default").mkdir()
        brave = self.fake_exe("brave.exe")
        launched = []
        playwright = mock.MagicMock()
        playwright.chromium.launch_persistent_context.side_effect = lambda *a, **k: launched.append(k) or "ctx"

        with mock.patch.object(browser_login, "browser_choices", return_value=browsers.browser_choices(brave)):
            self.assertEqual(browser_login._launch(playwright, profile, headless=False), "ctx")

        self.assertEqual(launched[0]["executable_path"], brave)
        self.assertFalse((profile / "Default").exists())
        self.assertTrue((profile / browser_login.COOKIES_FILE).exists())
        self.assertEqual((profile / browser_login.CHANNEL_FILE).read_text(encoding="utf-8"), f"exe:{brave}")

    def test_same_browser_keeps_profile(self) -> None:
        profile = Path(self.temp.name) / "profile"
        (profile / "Default").mkdir(parents=True)
        (profile / browser_login.CHANNEL_FILE).write_text("msedge", encoding="utf-8")
        playwright = mock.MagicMock()
        with mock.patch.object(browser_login, "browser_choices", return_value=browsers.browser_choices("")):
            browser_login._launch(playwright, profile, headless=True)
        self.assertTrue((profile / "Default").exists())


if __name__ == "__main__":
    unittest.main()
