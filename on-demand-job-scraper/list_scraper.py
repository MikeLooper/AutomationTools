"""
list_scraper.py — Drives the live browser through a job-search results page
(LinkedIn or Indeed), clicking each card in the list and scraping the job it
reveals.

This needs actual DOM interaction (click, wait, re-read), which is only
possible through the live-browser-attach Selenium session (see
page_fetcher.py / README's "Enabling the authenticated read" section) — a
plain HTTP fetch of a search-results page can't be clicked. If no debug port
is available, or the current tab isn't a card-list page, `scrape_all_cards`
/ `scrape_all_indeed_cards` return None so the caller can fall back to the
single-page flow.

LinkedIn's own CSS classes are hashed/build-generated (see extractors/
linkedin.py), so cards are found via an accessible, stable signal instead: a
"Dismiss {Job Title} job" button sits inside every card, and its nearest
`role="button"` ancestor is the clickable card itself. Clicking a card there
updates an in-page preview pane without navigating.

Indeed works differently (confirmed by testing against a live results page):
clicking a card's "View full details of ..." button (data-testid
"inner-view-details-pressable" — the one non-hashed, repeated-per-card
landmark) navigates the whole tab to a standalone job-view page
(indeed.com/viewjob?jk=...), not an in-place pane update, so each card needs
a click, scrape, then `driver.back()` to return to the list before the next
one. Sponsored cards route through an ad-click redirect
(indeed.com/pagead/clk) first, which doesn't always resolve to the job page
within a reasonable wait — those are skipped rather than retried, since
repeatedly re-clicking a paid ad card during a retry would rack up real ad
spend for the employer.

Indeed occasionally shows a "verifying you are human" bot-check (the same
markers extractors/indeed.py already watches for). That can't be solved by
this script — it's a real challenge meant for a person — so wherever it
might appear (the results list loading, a card's click landing on it, or
even after navigating back), the scrape pauses, surfaces the browser window,
and waits for a human to clear it before continuing on its own.
"""

import time
from typing import Any
from urllib.parse import urlparse

import uiautomation as auto
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from extractors.indeed import BLOCK_MARKERS as INDEED_BLOCK_MARKERS

CARD_XPATH = "//div[@role='button'][.//button[starts-with(@aria-label,'Dismiss') and contains(@aria-label,'job')]]"
DISMISS_BUTTON_XPATH = ".//button[starts-with(@aria-label,'Dismiss')]"

INDEED_CARD_BUTTON_XPATH = "//button[@data-testid='inner-view-details-pressable']"

HUMAN_CHECK_POLL_INTERVAL = 1.0
HUMAN_CHECK_REMINDER_INTERVAL = 20.0
HUMAN_CHECK_MAX_WAIT = 300.0


def _attach(port: int) -> webdriver.Chrome:
    options = Options()
    options.debugger_address = f"127.0.0.1:{port}"
    return webdriver.Chrome(options=options)


def _switch_to_linkedin_jobs_tab(driver: webdriver.Chrome) -> bool:
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        if "linkedin.com/jobs" in driver.current_url:
            return True
    return False


def _looks_like_job_title(title: str) -> bool:
    """LinkedIn briefly sets a generic placeholder ("Jobs | LinkedIn") while
    the preview pane is still loading, before settling on the real
    "{Job Title} | {Company} | LinkedIn". Waiting for just *any* title change
    catches that placeholder and scrapes stale/loading content, so this
    checks for the real pattern's two "|" separators specifically."""
    return title.count("|") >= 2


def _wait_for_update(driver: webdriver.Chrome, previous_title: str, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    stable_since: float | None = None
    last_seen = previous_title
    while time.monotonic() < deadline:
        current = driver.title
        if current != previous_title and _looks_like_job_title(current):
            if current == last_seen:
                if stable_since is not None and time.monotonic() - stable_since >= 0.3:
                    return
            else:
                stable_since = time.monotonic()
                last_seen = current
        time.sleep(0.15)


def _wait_for_description_to_settle(driver: webdriver.Chrome, timeout: float = 5.0) -> None:
    """
    The title can finish updating well before the job description body has
    rendered at all (confirmed by timing: title fully settled while "About
    the job" was still 0 characters, with a real ~0.5s gap before it
    appeared) — capturing page_source right after the title stabilizes can
    grab an empty/partial description, silently losing salary, location,
    languages, and tools (everything extracted from that text). Waiting for
    the page's rendered size to stop growing catches that render finishing.
    """
    deadline = time.monotonic() + timeout
    stable_since: float | None = None
    last_length = -1
    while time.monotonic() < deadline:
        current_length = len(driver.page_source)
        if current_length == last_length:
            if stable_since is not None and time.monotonic() - stable_since >= 0.3:
                return
        else:
            stable_since = time.monotonic()
            last_length = current_length
        time.sleep(0.15)


def scrape_all_cards(debug_port: int, extractor_module, attributes: list[str]) -> list[dict[str, Any]] | None:
    """
    Return one result dict (matching extractor_module.parse's return shape)
    per job card on the current LinkedIn search-results page, or None if the
    current tab isn't a card-list page at all (e.g. a direct job-view page,
    or not LinkedIn), so the caller can fall back to the single-page flow.
    """
    try:
        driver = _attach(debug_port)
    except Exception:
        return None

    if not _switch_to_linkedin_jobs_tab(driver):
        return None

    cards = driver.find_elements(By.XPATH, CARD_XPATH)
    if not cards:
        return None

    print(f"  Found {len(cards)} job cards in the list.")
    jobs: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for index in range(len(cards)):
        # Re-query every iteration: clicking a card can reflow/replace list
        # DOM nodes, which would make stale references from before the click
        # raise StaleElementReferenceException.
        cards = driver.find_elements(By.XPATH, CARD_XPATH)
        if index >= len(cards):
            break
        card = cards[index]

        try:
            label = card.find_element(By.XPATH, DISMISS_BUTTON_XPATH).get_attribute("aria-label") or ""
            title_hint = label.removeprefix("Dismiss ").removesuffix(" job") or f"card {index + 1}"
        except Exception:
            title_hint = f"card {index + 1}"

        try:
            previous_title = driver.title
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
            card.click()
            _wait_for_update(driver, previous_title)
            _wait_for_description_to_settle(driver)

            url = driver.current_url
            if url in seen_urls:
                continue
            seen_urls.add(url)

            html = driver.page_source
            result = extractor_module.parse(url, html, attributes)
            jobs.append(result)
            print(f"    [{index + 1}/{len(cards)}] {result['attributes'].get('Job Title') or title_hint}")
        except Exception as exc:  # noqa: BLE001
            print(f"    [{index + 1}/{len(cards)}] Error scraping '{title_hint}': {exc}")

    return jobs


def _switch_to_indeed_jobs_tab(driver: webdriver.Chrome) -> bool:
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        if "indeed.com/jobs" in driver.current_url:
            return True
    return False


def _looks_like_human_check(driver: webdriver.Chrome) -> bool:
    lowered = driver.page_source.lower()
    return any(marker in lowered for marker in INDEED_BLOCK_MARKERS)


def _bring_indeed_window_to_front() -> None:
    """
    Best-effort: raise the Chrome window showing Indeed so a human notices
    the challenge without having to go hunting for it. Never raises — this
    is a convenience on top of the console message below, not something the
    scrape should fail over if no matching window can be found/focused (e.g.
    running over RDP without an active console session, same limitation
    browser_reader.py already has for the address-bar read).
    """
    try:
        for window in auto.GetRootControl().GetChildren():
            if window.ClassName != "Chrome_WidgetWin_1":
                continue
            edit = window.EditControl(Name="Address and search bar")
            if not edit.Exists(0, 0):
                continue
            value_pattern = edit.GetValuePattern()
            address = value_pattern.Value if value_pattern else ""
            if "indeed.com" in address:
                auto.SetForegroundWindow(window.NativeWindowHandle)
                return
    except Exception:
        pass


def _wait_through_human_check(driver: webdriver.Chrome) -> None:
    """If Indeed is showing a "verifying you are human" challenge, surface
    the browser window and wait for a person to clear it before letting the
    caller continue. No-op if the challenge isn't showing."""
    if not _looks_like_human_check(driver):
        return

    print("  Indeed is asking you to verify you're human — switch to the browser and complete the check to continue...")
    _bring_indeed_window_to_front()

    deadline = time.monotonic() + HUMAN_CHECK_MAX_WAIT
    last_reminder = time.monotonic()
    while time.monotonic() < deadline:
        if not _looks_like_human_check(driver):
            print("  Verified — resuming.")
            return
        if time.monotonic() - last_reminder >= HUMAN_CHECK_REMINDER_INTERVAL:
            print("  Still waiting on the human-verification check...")
            last_reminder = time.monotonic()
        time.sleep(HUMAN_CHECK_POLL_INTERVAL)

    print("  Gave up waiting on the human-verification check after 5 minutes.")


def _indeed_title_hint(label: str, index: int) -> str:
    marker = "View full details of "
    idx = label.find(marker)
    hint = label[idx + len(marker):] if idx != -1 else label
    return hint.split(" at ")[0].strip() or f"card {index + 1}"


def _wait_for_indeed_job_page(driver: webdriver.Chrome, timeout: float = 12.0) -> bool:
    """Wait for the clicked card to land on a rendered job-detail page (its
    own `vj-job-title` element present). Returns False on timeout — a
    sponsored card's ad-click redirect (indeed.com/pagead/clk) doesn't
    always resolve within a reasonable wait, and that's treated as a skip
    rather than an error (see module docstring). A human-verification
    challenge mid-wait pauses the clock rather than counting against it —
    see `_wait_through_human_check`."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if driver.find_elements(By.CSS_SELECTOR, "[data-testid='vj-job-title']"):
            return True
        if _looks_like_human_check(driver):
            _wait_through_human_check(driver)
            deadline = time.monotonic() + timeout
            continue
        time.sleep(0.15)
    return False


def _wait_for_indeed_results_list(driver: webdriver.Chrome, timeout: float = 8.0) -> bool:
    """Wait for `driver.back()` to land back on the results list (its card
    buttons present again) before the next card is clicked."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if driver.find_elements(By.XPATH, INDEED_CARD_BUTTON_XPATH):
            return True
        if _looks_like_human_check(driver):
            _wait_through_human_check(driver)
            deadline = time.monotonic() + timeout
            continue
        time.sleep(0.15)
    return False


def scrape_all_indeed_cards(debug_port: int, extractor_module, attributes: list[str]) -> list[dict[str, Any]] | None:
    """
    Return one result dict (matching extractor_module.parse's return shape)
    per job card on the current Indeed search-results page, or None if the
    current tab isn't a card-list page at all (e.g. a direct job-view page,
    or not Indeed), so the caller can fall back to the single-page flow.

    Unlike LinkedIn, clicking a card navigates the whole tab to a standalone
    job-view page (see module docstring), so each iteration clicks, scrapes,
    then navigates back to the list before the next click.
    """
    try:
        driver = _attach(debug_port)
    except Exception:
        return None

    if not _switch_to_indeed_jobs_tab(driver):
        return None

    _wait_through_human_check(driver)

    buttons = driver.find_elements(By.XPATH, INDEED_CARD_BUTTON_XPATH)
    if not buttons:
        return None

    num_cards = len(buttons)
    print(f"  Found {num_cards} job cards in the list.")
    jobs: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for index in range(num_cards):
        # Re-query every iteration: navigating away and back can replace the
        # list's DOM nodes, which would make a stale reference from before
        # the click raise StaleElementReferenceException.
        buttons = driver.find_elements(By.XPATH, INDEED_CARD_BUTTON_XPATH)
        if index >= len(buttons):
            break
        button = buttons[index]
        title_hint = _indeed_title_hint(button.get_attribute("aria-label") or "", index)

        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
            button.click()

            landed = _wait_for_indeed_job_page(driver)
            hostname = urlparse(driver.current_url).hostname or ""
            if landed and (hostname == "indeed.com" or hostname.endswith(".indeed.com")):
                _wait_for_description_to_settle(driver)
                url = driver.current_url
                if url not in seen_urls:
                    seen_urls.add(url)
                    html = driver.page_source
                    result = extractor_module.parse(url, html, attributes)
                    jobs.append(result)
                    print(f"    [{index + 1}/{num_cards}] {result['attributes'].get('Job Title') or title_hint}")
            else:
                print(f"    [{index + 1}/{num_cards}] Skipped '{title_hint}': job details page didn't load (sponsored-listing redirect?).")
        except Exception as exc:  # noqa: BLE001
            print(f"    [{index + 1}/{num_cards}] Error scraping '{title_hint}': {exc}")
        finally:
            driver.back()
            _wait_for_indeed_results_list(driver)

    return jobs
