"""
list_scraper.py — Drives the live browser through a LinkedIn job-search
results page, clicking each card in the list and scraping the preview pane
that appears on click.

This needs actual DOM interaction (click, wait, re-read), which is only
possible through the live-browser-attach Selenium session (see
page_fetcher.py / README's "Enabling the authenticated read" section) — a
plain HTTP fetch of a search-results page can't be clicked. If no debug port
is available, or the current tab isn't a card-list page, `scrape_all_cards`
returns None so the caller can fall back to the single-page flow.

LinkedIn's own CSS classes are hashed/build-generated (see extractors/
linkedin.py), so cards are found via an accessible, stable signal instead: a
"Dismiss {Job Title} job" button sits inside every card, and its nearest
`role="button"` ancestor is the clickable card itself.
"""

import time
from typing import Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

CARD_XPATH = "//div[@role='button'][.//button[starts-with(@aria-label,'Dismiss') and contains(@aria-label,'job')]]"
DISMISS_BUTTON_XPATH = ".//button[starts-with(@aria-label,'Dismiss')]"


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
