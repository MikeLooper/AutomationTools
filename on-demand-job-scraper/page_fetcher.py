"""
page_fetcher.py — Retrieve the HTML for a URL, preferring a live, logged-in
browser session over a fresh anonymous HTTP request.

Two tiers:
  1. Live-browser attach: if a Chrome/Edge instance is already running with
     its remote debugging port enabled, connect to it via Selenium's
     `debugger_address` and read the exact tab's rendered `page_source`,
     cookies and all. NOTE: current Chrome/Edge refuse to open the debug
     port against your normal, default profile (a deliberate anti-session-
     theft protection) — this only works against a separate, dedicated
     profile (its own `--user-data-dir`) that you've already logged into.
     See README.md for how to set one up.
  2. Plain HTTP GET (`requests`) as a fallback. Works fine for public job
     boards; login-walled pages will come back thin or blocked, which is
     reported to the caller as a warning rather than failed silently.
"""

import os
from dataclasses import dataclass
from urllib.parse import urlparse
from pathlib import Path

import requests

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Where Chrome/Edge record their active debugging port, when one is enabled.
DEVTOOLS_PORT_FILES = [
    Path(os.environ.get("LOCALAPPDATA", "")) / r"Google\Chrome\User Data\DevToolsActivePort",
    Path(os.environ.get("LOCALAPPDATA", "")) / r"Microsoft\Edge\User Data\DevToolsActivePort",
]

# The debug port only actually opens against a dedicated, non-default
# profile (see README), whose --user-data-dir path we can't predict, so the
# file-based lookup above can't find it. Fall back to probing the port the
# README's example command uses directly.
DEFAULT_CANDIDATE_PORTS = [9222]

LOGIN_WALL_MARKERS = [
    "authwall", "join now to see", "sign in to continue", "please sign in",
    "log in to see", "session has expired",
]


@dataclass
class FetchResult:
    html: str
    method: str  # "live-browser" or "http"
    warning: str | None = None


def _probe_port(port: int) -> bool:
    try:
        return requests.get(f"http://127.0.0.1:{port}/json/version", timeout=1.5).ok
    except requests.RequestException:
        return False


def find_debug_port(extra_ports: list[int] | None = None) -> int | None:
    for path in DEVTOOLS_PORT_FILES:
        try:
            first_line = path.read_text(encoding="utf-8").splitlines()[0]
            port = int(first_line.strip())
        except (OSError, ValueError, IndexError):
            continue
        if _probe_port(port):
            return port

    for port in (extra_ports or []) + DEFAULT_CANDIDATE_PORTS:
        if _probe_port(port):
            return port
    return None


def _fetch_via_live_browser(url: str, port: int) -> str | None:
    """Attach to the already-running browser and read the matching tab's DOM."""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.debugger_address = f"127.0.0.1:{port}"
    driver = webdriver.Chrome(options=options)
    try:
        def _normalize(u: str) -> str:
            # Chrome's own address bar elides the "www." subdomain and a
            # trailing slash for display, so a URL read from it (via
            # browser_reader.py's UI Automation read) never matches
            # driver.current_url exactly unless both are normalized the
            # same way here.
            no_fragment = u.split("#")[0].rstrip("/")
            parsed = urlparse(no_fragment)
            host = parsed.netloc[4:] if parsed.netloc.startswith("www.") else parsed.netloc
            return f"{host}{parsed.path}?{parsed.query}" if parsed.query else f"{host}{parsed.path}"

        target = None
        for handle in driver.window_handles:
            driver.switch_to.window(handle)
            if driver.current_url == url or _normalize(driver.current_url) == _normalize(url):
                target = handle
                break
        if target is None:
            # No tab matched the URL exactly (e.g. it redirected or query
            # params differ slightly) — don't guess; let the caller fall
            # back to a plain HTTP fetch instead of returning the wrong tab.
            return None
        return driver.page_source
    finally:
        # Do NOT call driver.quit() here: this session is attached to the
        # user's real browser, not one Selenium launched, and quitting can
        # close their actual window/tabs.
        pass


def open_in_browser(port: int, file_path: Path) -> bool:
    """
    Open a local file as a new tab in the browser attached at `port`, rather
    than whatever the OS considers the default browser (`os.startfile`),
    since it's often a different profile/window than the one this process
    was actually working in. Returns False on any failure so the caller can
    fall back to `os.startfile`.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.debugger_address = f"127.0.0.1:{port}"
    try:
        driver = webdriver.Chrome(options=options)
        driver.switch_to.new_window("tab")
        driver.get(Path(file_path).resolve().as_uri())
        return True
    except Exception:  # noqa: BLE001
        return False


def _looks_login_walled(html: str) -> bool:
    lowered = html.lower()
    if any(marker in lowered for marker in LOGIN_WALL_MARKERS):
        return True
    return len(html) < 2000


def fetch(url: str, debug_port: int | None = None) -> FetchResult:
    port = find_debug_port(extra_ports=[debug_port] if debug_port else None)
    if port is not None:
        try:
            html = _fetch_via_live_browser(url, port)
            if html:
                return FetchResult(html=html, method="live-browser")
        except Exception as exc:  # noqa: BLE001
            print(f"  [page_fetcher] Live-browser attach failed ({exc}); falling back to HTTP.")

    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not fetch {url}: {exc}") from exc

    warning = None
    if _looks_login_walled(resp.text):
        warning = (
            "This page may require your logged-in session to show full details, and only a "
            "plain, unauthenticated request could be made. Modern Chrome/Edge refuse to open "
            "the remote-debugging port on your default profile (this is intentional hardening "
            "against exactly this kind of session reading), so the live-browser-attach path "
            "only works against a separate, dedicated browser profile that's already logged "
            "into the sites you need — see README.md for how to set one up."
        )
    return FetchResult(html=resp.text, method="http", warning=warning)
