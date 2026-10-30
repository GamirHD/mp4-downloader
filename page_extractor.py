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


def sniff_media_with_browser(
    page_url: str,
    cookiejar: Any = None,
    *,
    timeout_seconds: float = 25,
    log: Callable[[str], None] = print,
) -> EmbeddedMedia | None:
    """Open the page headless and record the video stream it requests."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log(
            "Tipp: Fuer Seiten, die das Video per JavaScript laden, "
            "`pip install playwright` und `python -m playwright install chromium` ausfuehren."
        )
        return None

    found: list[str] = []

    def on_request(request: Any) -> None:
        url = request.url
        if is_media_url(url) and url not in found:
            found.append(url)

    log("Oeffne die Seite im Hintergrund-Browser und suche den Videostream...")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            cookies = _playwright_cookies(cookiejar, page_url)
            if cookies:
                context.add_cookies(cookies)
            page = context.new_page()
            page.on("request", on_request)
            page.goto(page_url, wait_until="domcontentloaded", timeout=int(timeout_seconds * 1000))
            title = None
            try:
                title = page.title()
            except Exception:  # noqa: BLE001 - title is optional
                pass

            waited = 0.0
            step = 0.5
            while waited < timeout_seconds and not any(_media_rank(u)[0] < 2 for u in found):
                if waited in (2.0, 6.0):
                    _try_start_playback(page)
                page.wait_for_timeout(int(step * 1000))
                waited += step
            # Give the player a moment to request the master playlist too.
            if found:
                page.wait_for_timeout(1000)
        finally:
            browser.close()

    if not found:
        return None
    return EmbeddedMedia(page_url=page_url, title=clean_title(title), media_urls=sort_media_urls(found))


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

    if page_html:
        media_urls = find_media_in_html(page_html, page_url)
        if media_urls:
            log(f"Eingebettetes Video im Seiten-HTML gefunden ({len(media_urls)} Kandidat(en)).")
            return EmbeddedMedia(page_url=page_url, title=extract_page_title(page_html), media_urls=media_urls)

    if not use_browser:
        return None
    media = sniff_media_with_browser(page_url, getattr(downloader, "cookiejar", None), log=log)
    if media and not media.title and page_html:
        media.title = extract_page_title(page_html)
    return media
