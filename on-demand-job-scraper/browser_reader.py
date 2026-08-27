"""
browser_reader.py — Find the URL currently open in the system's web browser.

Reads the address bar of the foreground (or, if ambiguous, user-selected)
browser window using Windows UI Automation (`uiautomation`). This only reads
the browser's own toolbar UI, not page content, so it works instantly without
needing any special browser flags or restarts.
"""

import uiautomation as auto

CHROMIUM_WINDOW_CLASS = "Chrome_WidgetWin_1"
FIREFOX_WINDOW_CLASS = "MozillaWindowClass"
BROWSER_WINDOW_CLASSES = (CHROMIUM_WINDOW_CLASS, FIREFOX_WINDOW_CLASS)

CHROMIUM_ADDRESS_BAR_NAME = "Address and search bar"
FIREFOX_ADDRESS_BAR_AUTOMATION_ID = "urlbar-input"

auto.SetGlobalSearchTimeout(3)


class BrowserNotFoundError(RuntimeError):
    pass


def _address_bar_value(window: auto.Control) -> str | None:
    if window.ClassName == CHROMIUM_WINDOW_CLASS:
        edit = window.EditControl(Name=CHROMIUM_ADDRESS_BAR_NAME)
    elif window.ClassName == FIREFOX_WINDOW_CLASS:
        edit = window.EditControl(AutomationId=FIREFOX_ADDRESS_BAR_AUTOMATION_ID)
    else:
        return None

    if not edit.Exists(0, 0):
        return None
    value_pattern = edit.GetValuePattern()
    if not value_pattern:
        return None
    return value_pattern.Value


def _normalize_url(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return raw
    if "://" not in raw:
        raw = f"https://{raw}"
    return raw


def _list_browser_windows() -> list[auto.Control]:
    """
    Return actual browser windows only. Matching on window class alone isn't
    enough: many Chromium-based Electron apps (Slack, Discord, the Claude
    desktop app, etc.) share the same `Chrome_WidgetWin_1` class as real
    Chrome/Edge windows. Requiring a readable address bar filters those out,
    since only a real browser window has one.
    """
    windows = []
    for child in auto.GetRootControl().GetChildren():
        if child.ClassName in BROWSER_WINDOW_CLASSES and _address_bar_value(child) is not None:
            windows.append(child)
    return windows


def get_active_browser_url() -> tuple[str, str]:
    """
    Return (url, window_title) for the page currently open in the system browser.

    Prefers the foreground window if it's a real browser window; otherwise
    looks at all open browser windows, using the only one found or asking the
    user to pick when more than one is open.
    """
    foreground = auto.GetForegroundControl()
    all_browsers = _list_browser_windows()

    if foreground.ClassName in BROWSER_WINDOW_CLASSES and any(
        foreground.NativeWindowHandle == w.NativeWindowHandle for w in all_browsers
    ):
        candidates = [foreground]
    else:
        candidates = all_browsers

    if not candidates:
        raise BrowserNotFoundError(
            "No open Chrome, Edge, or Firefox window was found. Open the job "
            "posting in your browser and run this tool again."
        )

    if len(candidates) > 1:
        print("Multiple browser windows are open:")
        for idx, win in enumerate(candidates, start=1):
            print(f"  [{idx}] {win.Name}")
        choice = input(f"Which window has the job posting? [1-{len(candidates)}]: ").strip()
        try:
            window = candidates[int(choice) - 1]
        except (ValueError, IndexError):
            raise BrowserNotFoundError("Invalid selection.")
    else:
        window = candidates[0]

    raw_url = _address_bar_value(window)
    if not raw_url:
        raise BrowserNotFoundError(
            f"Could not read the address bar of window '{window.Name}'."
        )
    return _normalize_url(raw_url), window.Name
