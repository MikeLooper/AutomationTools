"""
extractors/topresume.py — Extractor for careerio.topresume.com job search results.

TopResume search pages are heavily JavaScript-driven, so this extractor drives
a real browser: it activates the `Search` tab (as opposed to the
`Recommended Jobs` tab), reads each job card's own link to the job
description (never the card's `Apply` link), opens it to load the
description panel on the right side of the page, and scrapes the rendered
text. If the page redirects to the sign-in flow, extraction stops and the
user is notified that they need to sign in first.
"""

from typing import Any
from urllib.parse import urljoin, urlparse

from extractors.base import BaseExtractor, extract_attributes


SIGN_IN_URL_MARKER = "auth/sign-in"


class TopResumeSignInRequiredError(RuntimeError):
    """Raised when TopResume redirects to its sign-in page."""


class TopResumeExtractor(BaseExtractor):
    @staticmethod
    def _is_probable_job_link(href: str) -> bool:
        lower = href.lower()
        if "job-search" in lower:
            return False
        return (
            "/job/" in lower
            or "/jobs/" in lower
            or "jobid=" in lower
            or "job_id=" in lower
            or "/app/job" in lower
        )

    @staticmethod
    def _normalize_job_url(base_url: str, href: str) -> str:
        return urljoin(base_url, href.strip())

    @staticmethod
    def _is_apply_link(element) -> bool:
        """Return True when `element` looks like the card's Apply control."""
        try:
            text = (element.text or "").strip().lower()
        except Exception:
            text = ""
        aria_label = (element.get_attribute("aria-label") or "").strip().lower()
        testid = (element.get_attribute("data-testid") or "").strip().lower()
        class_name = (element.get_attribute("class") or "").strip().lower()
        return "apply" in " ".join([text, aria_label, testid, class_name])

    def _check_signed_in(self, driver) -> None:
        current_url = (driver.current_url or "").lower()
        if SIGN_IN_URL_MARKER in current_url:
            message = (
                "TopResume redirected to sign-in. Please sign in to "
                "https://careerio.topresume.com and re-run the job search "
                "before TopResume listings can be processed."
            )
            print(f"  [TopResume] {message}")
            raise TopResumeSignInRequiredError(message)

    def _find_search_tab(self, driver):
        from selenium.webdriver.common.by import By

        tabs = driver.find_elements(By.CSS_SELECTOR, "[role='tab']")
        if not tabs:
            tabs = driver.find_elements(
                By.XPATH,
                "//*[normalize-space(text())='Search' "
                "or starts-with(normalize-space(text()), 'Recommended Jobs')]",
            )

        search_tab = None
        fallback_tab = None
        for tab in tabs:
            try:
                label = (tab.text or "").strip().lower()
            except Exception:
                continue
            if not label or label.startswith("recommended jobs"):
                continue
            if label == "search":
                search_tab = tab
                break
            if fallback_tab is None and label.startswith("search"):
                fallback_tab = tab

        return search_tab or fallback_tab

    @staticmethod
    def _scope_to_search_panel(driver, search_tab):
        from selenium.webdriver.common.by import By

        if search_tab is not None:
            panel_id = (search_tab.get_attribute("aria-controls") or "").strip()
            if panel_id:
                try:
                    return driver.find_element(By.ID, panel_id)
                except Exception:
                    pass

        for panel in driver.find_elements(By.CSS_SELECTOR, "[role='tabpanel']"):
            try:
                if panel.is_displayed():
                    return panel
            except Exception:
                continue

        return None

    @classmethod
    def _find_card_detail_link(cls, card):
        from selenium.webdriver.common.by import By

        candidates = []

        self_href = (card.get_attribute("href") or "").strip()
        if self_href and not self_href.startswith("javascript:") and not cls._is_apply_link(card):
            candidates.append(card)

        for anchor in card.find_elements(By.CSS_SELECTOR, "a[href]"):
            href = (anchor.get_attribute("href") or "").strip()
            if not href or href.startswith("javascript:"):
                continue
            if cls._is_apply_link(anchor):
                continue
            candidates.append(anchor)

        if not candidates:
            return None

        for anchor in candidates:
            href = (anchor.get_attribute("href") or "").strip()
            if cls._is_probable_job_link(href):
                return anchor

        return candidates[0]

    def _find_card_detail_url(self, card, base_url: str) -> str:
        link = self._find_card_detail_link(card)
        if link is None:
            return ""
        href = (link.get_attribute("href") or "").strip()
        if not href:
            return ""
        return self._normalize_job_url(base_url, href).split("#", 1)[0]

    def _extract(
        self,
        driver,
        url: str,
        attributes: list[str],
    ) -> list[dict[str, Any]]:
        driver.get(url)
        self.sleep(5)
        self._check_signed_in(driver)

        search_tab = self._find_search_tab(driver)
        if search_tab is not None:
            is_selected = (search_tab.get_attribute("aria-selected") or "").strip().lower() == "true"
            if not is_selected:
                driver.execute_script("arguments[0].click();", search_tab)
                self.sleep(1.5)
                self._check_signed_in(driver)
        else:
            print("  [TopResume] Could not locate the 'Search' tab; reading cards from the full page.")

        container = self._scope_to_search_panel(driver, search_tab)
        scope = container if container is not None else driver

        # Trigger lazy-loaded content in the results panel.
        for _ in range(3):
            driver.execute_script("window.scrollBy(0, document.body.scrollHeight * 0.6);")
            if container is not None:
                driver.execute_script(
                    "if (arguments[0]) { arguments[0].scrollTop = arguments[0].scrollHeight; }",
                    container,
                )
            self.sleep(1.2)

        return self._extract_search_cards(driver, scope, url, attributes)

    def _extract_search_cards(
        self,
        driver,
        scope,
        url: str,
        attributes: list[str],
    ) -> list[dict[str, Any]]:
        from selenium.webdriver.common.by import By

        card_selectors = [
            "[data-testid*='job-card']",
            "[data-testid*='job-result']",
            "div[class*='job-card']",
            "div[class*='job-result']",
            "li[class*='job']",
            "article[class*='job']",
        ]

        cards = []
        for sel in card_selectors:
            cards = scope.find_elements(By.CSS_SELECTOR, sel)
            if cards:
                break

        print(f"  [TopResume] Found {len(cards)} job cards (Search tab)")
        if not cards:
            return []

        jobs: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for idx, card in enumerate(cards):
            try:
                job_url = self._find_card_detail_url(card, url)
                if not job_url or job_url in seen_urls:
                    continue

                link_el = self._find_card_detail_link(card)
                click_target = link_el if link_el is not None else card
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", click_target)
                self.sleep(0.5)
                driver.execute_script("arguments[0].click();", click_target)
                self.sleep(1.8)
                self._check_signed_in(driver)

                title = ""
                for sel in ["h1", "[data-testid*='job-title']", "[data-testid*='title']", "[class*='title']"]:
                    try:
                        el = driver.find_element(By.CSS_SELECTOR, sel)
                        title = (el.text or "").strip()
                        if title:
                            break
                    except Exception:
                        pass

                detail_text = ""
                for sel in [
                    "[data-testid*='description']",
                    "[class*='description']",
                    "main",
                    "article",
                    "body",
                ]:
                    try:
                        panel = driver.find_element(By.CSS_SELECTOR, sel)
                        detail_text = (panel.text or "").strip()
                        if detail_text:
                            break
                    except Exception:
                        pass

                if not title:
                    title = (card.text or "").split("\n", 1)[0].strip()

                attrs = extract_attributes(detail_text, attributes)
                if title and "Job Title" in attrs:
                    attrs["Job Title"] = title

                seen_urls.add(job_url)
                jobs.append({"job_url": job_url, "attributes": attrs})
                print(f"    [{idx+1}] {attrs.get('Job Title', '?')}")
            except TopResumeSignInRequiredError:
                raise
            except Exception as exc:
                print(f"    [TopResume] Error on card {idx+1}: {exc}")

        return jobs
