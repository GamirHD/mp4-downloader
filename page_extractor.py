"""Find videos that are embedded in normal web pages.

yt-dlp knows many video sites, but course platforms and other sites with
their own player are often reported as "Unsupported URL". For those pages
this module looks for the real media stream (HLS ``.m3u8``, DASH ``.mpd``,
``.mp4``) or a known player iframe:

1. Read the page HTML (with the user's browser cookies, so pages behind a
   login work) and search it for media links.
2. If nothing is in the HTML because the player builds the link with
   JavaScript, optionally open the page in a headless browser (Playwright)
   and watch the network requests for the stream, the same way you would
   in the browser's developer tools.

DRM-protected streams are not handled; yt-dlp refuses those on its own.
"""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

MEDIA_URL_PATTERN = re.compile(
    r"""https?:(?:\\?/){2}[^\s"'<>()]+?\.(?:m3u8|mpd|mp4)(?:\?[^\s"'<>()]*)?(?=[\s"'<>()]|$)""",
    re.IGNORECASE,
)
IFRAME_SRC_PATTERN = re.compile(r"""<iframe\b[^>]*?\bsrc\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
VIDEO_SRC_PATTERN = re.compile(r"""<(?:video|source)\b[^>]*?\bsrc\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
TITLE_PATTERNS = (
    re.compile(r"""<meta[^>]+property=["']og:title["'][^>]+content=["']([^"']+)["']""", re.IGNORECASE),
    re.compile(r"""<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:title["']""", re.IGNORECASE),
    re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL),
)
KNOWN_PLAYER_HOSTS = (
    "player.vimeo.com",
    "vimeo.com",
    "youtube.com",
    "youtube-nocookie.com",
    "youtu.be",
    "kaltura.com",
    "kaltura.net",
    "jwplayer.com",
    "jwplatform.com",
    "mux.com",
    "mediadelivery.net",
    "b-cdn.net",
    "wistia.com",
    "wistia.net",
    "vidyard.com",
    "brightcove.net",
    "cloudflarestream.com",
    "videodelivery.net",
    "dailymotion.com",
    "streamable.com",
    "loom.com",
    "spotlightr.com",
    "vidalytics.com",
)
TITLE_SITE_SUFFIX_PATTERN = re.compile(r"\s+[|–—]\s+[^|–—]{1,40}$")
SEGMENT_HINT_PATTERN = re.compile(r"(?:^|/)(?:seg|segment|chunk|frag)[-_]?\d", re.IGNORECASE)


@dataclass
class EmbeddedMedia:
    page_url: str
    title: str | None = None
    media_urls: list[str] = field(default_factory=list)

    @property
    def referer_headers(self) -> dict[str, str]:
        return referer_headers(self.page_url)


def referer_headers(page_url: str) -> dict[str, str]:
    parsed = urlparse(page_url)
    return {"Referer": page_url, "Origin": f"{parsed.scheme}://{parsed.netloc}"}


def _clean_url(raw: str, page_url: str) -> str:
    url = raw.replace("\\/", "/").replace("\\u0026", "&").replace("\\u002F", "/")
    url = html_lib.unescape(url).strip().rstrip("\\")
    if url.startswith("//"):
        url = f"{urlparse(page_url).scheme or 'https'}:{url}"
    return urljoin(page_url, url)


def _is_known_player(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == known or host.endswith(f".{known}") for known in KNOWN_PLAYER_HOSTS)


def _media_rank(url: str) -> tuple[int, int]:
    path = urlparse(url).path.lower()
    if path.endswith(".m3u8"):
        kind = 0
    elif path.endswith(".mpd"):
        kind = 1
    else:
        kind = 2
    name = path.rsplit("/", 1)[-1]
    # Prefer master playlists that contain all qualities over single variants.
    preference = 0 if any(word in name for word in ("master", "index", "playlist", "manifest")) else 1
    return kind, preference


def is_media_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    if SEGMENT_HINT_PATTERN.search(path.rsplit("/", 1)[-1]):
        return False
    return path.endswith((".m3u8", ".mpd", ".mp4"))


def sort_media_urls(urls: list[str]) -> list[str]:
    unique = list(dict.fromkeys(urls))
    return sorted(unique, key=_media_rank)


def clean_title(title: str | None) -> str | None:
    """Drop a trailing site name like "Kursname | GA.GG"."""
    if not title:
        return None
    text = re.sub(r"\s+", " ", title).strip()
    shortened = TITLE_SITE_SUFFIX_PATTERN.sub("", text).strip()
    return shortened or text or None


def extract_page_title(page_html: str) -> str | None:
    for pattern in TITLE_PATTERNS:
        match = pattern.search(page_html)
        if match:
            title = clean_title(html_lib.unescape(match.group(1)))
            if title:
                return title
    return None


def find_media_in_html(page_html: str, page_url: str) -> list[str]:
    """Return candidate video URLs from a page, best candidates first."""
    direct: list[str] = []
    for match in MEDIA_URL_PATTERN.finditer(page_html):
        url = _clean_url(match.group(0), page_url)
        if is_media_url(url):
            direct.append(url)
    for match in VIDEO_SRC_PATTERN.finditer(page_html):
        url = _clean_url(match.group(1), page_url)
        if url.startswith("http") and not url.startswith("blob:") and is_media_url(url):
            direct.append(url)

    players: list[str] = []
    for match in IFRAME_SRC_PATTERN.finditer(page_html):
        url = _clean_url(match.group(1), page_url)
        if url.startswith("http") and _is_known_player(url):
            players.append(url)

    return sort_media_urls(direct) + list(dict.fromkeys(players))


def _playwright_cookies(cookiejar: Any, page_url: str) -> list[dict[str, Any]]:
    """Only pass cookies of the page's own site to the headless browser."""
    host = (urlparse(page_url).hostname or "").lower()
    is_ip_address = bool(re.fullmatch(r"[\d.]+|[0-9a-f:]+", host))
    site = host if is_ip_address else ".".join(host.split(".")[-2:])
    cookies: list[dict[str, Any]] = []
    for cookie in cookiejar or []:
        domain = (cookie.domain or "").lstrip(".").lower()
        if not domain or not (domain == site or domain.endswith(f".{site}")):
            continue
        cookies.append(
            {
                "name": cookie.name,
                "value": cookie.value or "",
                "domain": cookie.domain,
                "path": cookie.path or "/",
                "expires": float(cookie.expires) if cookie.expires else -1,
                "secure": bool(cookie.secure),
                "httpOnly": bool(cookie.has_nonstandard_attr("HttpOnly")),
            }
        )
    return cookies


MANIFEST_CONTENT_TYPES = (
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "audio/mpegurl",
    "audio/x-mpegurl",
    "application/dash+xml",
)
LOGIN_HINT_PATTERN = re.compile(r"login|anmelden|sign-?in|signin|auth", re.IGNORECASE)


def _strip_query(url: str) -> str:
    return url.split("?", 1)[0]


def _launch_browser(playwright: Any, log: Callable[[str], None]) -> Any:
    """Prefer an installed Edge/Chrome (looks like a normal browser, no download needed)."""
    errors: list[str] = []
    for channel in ("msedge", "chrome", None):
        try:
            if channel:
                return playwright.chromium.launch(headless=True, channel=channel)
            return playwright.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001 - try the next browser
            errors.append(f"{channel or 'chromium'}: {str(exc).splitlines()[0]}")
    raise RuntimeError(
        "Kein Browser fuer die Video-Suche gefunden. Installiere Microsoft Edge oder Chrome, "
        "oder fuehre `python -m playwright install chromium` aus. (" + "; ".join(errors) + ")"
    )


def sniff_media_with_browser(
    page_url: str,
    cookiejar: Any = None,
    *,
    timeout_seconds: float = 40,
    debug_dir: Path | None = None,
    log: Callable[[str], None] = print,
) -> EmbeddedMedia | None:
    """Open the page headless and record the video stream it requests."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log(
            "Tipp: Fuer Seiten, die das Video per JavaScript laden, "
            "`python -m pip install playwright` ausfuehren."
        )
        return None

    found: list[str] = []
    request_log: list[str] = []
    segments_seen = 0

    def remember(url: str) -> None:
        if url not in found:
            found.append(url)

    def on_request(request: Any) -> None:
        nonlocal segments_seen
        url = request.url
        if is_media_url(url):
            remember(url)
        elif _strip_query(url).lower().endswith((".ts", ".m4s", ".aac")):
            segments_seen += 1

    def on_response(response: Any) -> None:
        url = response.url
        try:
            content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        except Exception:  # noqa: BLE001 - headers may be unavailable
            content_type = ""
        if content_type in MANIFEST_CONTENT_TYPES:
            remember(url)
        if debug_dir is not None:
            request_log.append(f"{response.status}  {content_type or '-':<32}  {_strip_query(url)}")

    title = None
    final_url = page_url
    log("Oeffne die Seite im Hintergrund-Browser und suche den Videostream...")
    with sync_playwright() as playwright:
        browser = _launch_browser(playwright, log)
        try:
            user_agent = browser.new_page().evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome")
            context = browser.new_context(
                user_agent=user_agent,
                viewport={"width": 1600, "height": 900},
                locale="de-DE",
            )
            cookies = _playwright_cookies(cookiejar, page_url)
            if cookies:
                context.add_cookies(cookies)
            log(f"Login-Cookies fuer den Hintergrund-Browser: {len(cookies)}")
            context.on("request", on_request)
            context.on("response", on_response)
            page = context.new_page()
            page.goto(page_url, wait_until="domcontentloaded", timeout=int(timeout_seconds * 1000))

            def has_manifest() -> bool:
                return any(_media_rank(u)[0] < 2 for u in found)

            waited = 0.0
            step = 0.5
            while waited < timeout_seconds and not has_manifest():
                if waited in (3.0, 10.0, 20.0):
                    _try_start_playback(page)
                if waited in (6.0, 14.0, 26.0):
                    _click_player(page)
                page.wait_for_timeout(int(step * 1000))
                waited += step
            # Give the player a moment to request the master playlist too.
            if found:
                page.wait_for_timeout(1500)

            try:
                title = page.title()
                final_url = page.url
            except Exception:  # noqa: BLE001 - optional information
                pass
            if debug_dir is not None:
                _write_debug(debug_dir, page, request_log, found, final_url, len(cookies), log)
        finally:
            browser.close()

    if not found:
        if final_url.split("#")[0].rstrip("/") != page_url.split("#")[0].rstrip("/"):
            log(f"Der Hintergrund-Browser wurde weitergeleitet auf: {_strip_query(final_url)}")
            if LOGIN_HINT_PATTERN.search(final_url):
                log("Das sieht nach einer Login-Seite aus: die Cookies sind abgelaufen oder fehlen.")
        if segments_seen:
            log(f"Es wurden {segments_seen} Video-Teile geladen, aber keine Playlist erkannt.")
        return None
    return EmbeddedMedia(page_url=page_url, title=clean_title(title), media_urls=sort_media_urls(found))


def _write_debug(
    debug_dir: Path,
    page: Any,
    request_log: list[str],
    found: list[str],
    final_url: str,
    cookie_count: int,
    log: Callable[[str], None],
) -> None:
    debug_dir.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(debug_dir / "browser.png"), full_page=False)
    except Exception:  # noqa: BLE001 - debugging is best effort
        pass
    frames = []
    for frame in page.frames:
        frames.append(_strip_query(frame.url))
    summary = [
        f"Endgueltige Adresse: {_strip_query(final_url)}",
        f"Login-Cookies uebergeben: {cookie_count}",
        f"Gefundene Streams: {len(found)}",
        *[f"  {_strip_query(url)}" for url in found],
        f"Frames ({len(frames)}):",
        *[f"  {url}" for url in frames],
        "",
        f"Anfragen ({len(request_log)}), Status / Typ / Adresse ohne Parameter:",
        *request_log,
    ]
    (debug_dir / "requests.txt").write_text("\n".join(summary), encoding="utf-8")
    log(f"Diagnose gespeichert in: {debug_dir}")


def _click_player(page: Any) -> None:
    """Click the middle of the biggest video-like element (players often need a click)."""
    script = """
    () => {
      const items = [...document.querySelectorAll('video, iframe, [class*="player" i], [id*="player" i]')]
        .map(el => ({el, r: el.getBoundingClientRect()}))
        .filter(({r}) => r.width > 200 && r.height > 120);
      items.sort((a, b) => b.r.width * b.r.height - a.r.width * a.r.height);
      if (!items.length) return null;
      items[0].el.scrollIntoView({block: 'center'});
      const r = items[0].el.getBoundingClientRect();
      return {x: r.left + r.width / 2, y: r.top + r.height / 2};
    }
    """
    try:
        point = page.evaluate(script)
        if point:
            page.mouse.click(point["x"], point["y"])
    except Exception:  # noqa: BLE001 - best effort
        pass


def _try_start_playback(page: Any) -> None:
    script = """
    () => {
      for (const video of document.querySelectorAll('video')) {
        video.muted = true;
        try { video.play(); } catch (e) {}
      }
      const button = document.querySelector(
        '[aria-label*="play" i], [title*="play" i], [class*="play" i] button, button[class*="play" i]'
      );
      if (button) { try { button.click(); } catch (e) {} }
    }
    """
    for frame in page.frames:
        try:
            frame.evaluate(script)
        except Exception:  # noqa: BLE001 - cross-origin or detached frames
            continue


def find_embedded_media(
    downloader: Any,
    page_url: str,
    *,
    use_browser: bool = True,
    debug_dir: Path | None = None,
    log: Callable[[str], None] = print,
) -> EmbeddedMedia | None:
    """Look for an embedded video on ``page_url`` using a yt-dlp ``YoutubeDL``."""
    page_html = ""
    try:
        response = downloader.urlopen(page_url)
        charset = response.headers.get_content_charset() if hasattr(response.headers, "get_content_charset") else None
        page_html = response.read().decode(charset or "utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - try the browser fallback anyway
        log(f"Seite konnte nicht gelesen werden: {exc}")

    if page_html and debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / "page.html").write_text(page_html, encoding="utf-8")

    if page_html:
        media_urls = find_media_in_html(page_html, page_url)
        if media_urls:
            log(f"Eingebettetes Video im Seiten-HTML gefunden ({len(media_urls)} Kandidat(en)).")
            return EmbeddedMedia(page_url=page_url, title=extract_page_title(page_html), media_urls=media_urls)

    if not use_browser:
        return None
    try:
        media = sniff_media_with_browser(
            page_url, getattr(downloader, "cookiejar", None), debug_dir=debug_dir, log=log
        )
    except Exception as exc:  # noqa: BLE001 - report and fall through to "nothing found"
        log(f"Hintergrund-Browser fehlgeschlagen: {exc}")
        media = None
    if media and not media.title and page_html:
        media.title = extract_page_title(page_html)
    return media
