"""
extractors/indeed.py — Extractor for indeed.com job search results.

Indeed uses a split layout: job cards down the left side of the page and a
detail pane on the right that shows the full description for whichever job
is currently selected.

Clicking a card in an automated Chrome session does not reliably update the
detail pane — Indeed's own front-end script silently ignores the click
(chromedriver leaves a well-known automation fingerprint on the page, e.g.
`window.cdc_...` globals, that anti-bot scripts commonly check for). Instead,
this extractor selects each job the same way Indeed's own shareable search
links do: by setting the `vjk` query parameter on the search-results URL to
that job's key and reloading. This produces the same end result — the right
pane shows that job's full description — without depending on a click
handler that gets suppressed.

Indeed occasionally interrupts anonymous browsing with a "verifying you are
human" interstitial. When that happens, extraction pauses so a person can
click the verification checkbox in the visible browser window, then resumes
automatically once the interstitial clears.
"""

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from selenium import webdriver
from selenium.webdriver.common.by import By

from extractors.base import BaseExtractor, extract_attributes


class IndeedExtractor(BaseExtractor):
    CARD_SELECTORS = [
        "div.job_seen_beacon",
        "td.resultContent",
        "li[data-testid='slider_item']",
        "div[class*='cardOutline']",
    ]

    DETAIL_SELECTORS = [
        "#jobsearch-ViewjobPaneWrapper",
        "div.jobsearch-JobComponent",
        "#jobsearch-ViewJobPaneWrapper",
        "main",
    ]

    DETAIL_TITLE_SELECTORS = [
        "[data-testid='vj-job-title']",
        "h2.jobsearch-JobInfoHeader-title",
        "[data-testid='jobsearch-JobInfoHeader-title']",
    ]

    @staticmethod
    def _safe_text(el) -> str:
        try:
            return (el.text or "").strip()
        except Exception:
            return ""

    def _find_cards(self, driver: webdriver.Chrome):
        for selector in self.CARD_SELECTORS:
            cards = driver.find_elements(By.CSS_SELECTOR, selector)
            cards = [card for card in cards if self._safe_text(card)]
            if cards:
                return cards
        return []

    def _card_job_key(self, card) -> str:
        """Return a stable identifier for a card (Indeed's `data-jk` job key)."""
        try:
            jk = card.get_attribute("data-jk")
            if jk:
                return jk
        except Exception:
            pass
        try:
            link = card.find_element(By.CSS_SELECTOR, "a[data-jk]")
            jk = link.get_attribute("data-jk")
            if jk:
                return jk
        except Exception:
            pass
        try:
            link = card.find_element(By.CSS_SELECTOR, "a[href*='jk=']")
            href = link.get_attribute("href") or ""
            match = re.search(r"jk=([a-f0-9]+)", href)
            if match:
                return match.group(1)
        except Exception:
            pass
        return ""

    @staticmethod
    def _url_with_vjk(url: str, job_key: str) -> str:
        """Return `url` with its `vjk` query parameter set to `job_key`."""
        parts = urlsplit(url)
        pairs = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() != "vjk"
        ]
        pairs.append(("vjk", job_key))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), parts.fragment))

    def _read_detail_text(self, driver: webdriver.Chrome) -> str:
        for selector in self.DETAIL_SELECTORS:
            try:
                panel = driver.find_element(By.CSS_SELECTOR, selector)
                text = self._safe_text(panel)
                if text:
                    return text
            except Exception:
                pass
        try:
            return self._safe_text(driver.find_element(By.TAG_NAME, "body"))
        except Exception:
            return ""

    def _read_detail_title(self, driver: webdriver.Chrome) -> str:
        for selector in self.DETAIL_TITLE_SELECTORS:
            try:
                el = driver.find_element(By.CSS_SELECTOR, selector)
                text = self._safe_text(el)
                if text:
                    return text
            except Exception:
                pass
        return ""

    def _extract(
        self,
        driver: webdriver.Chrome,
        url: str,
        attributes: list[str],
    ) -> list[dict[str, Any]]:
        driver.get(url)
        self.sleep(3)
        self.wait_for_human_verification(driver)

        cards = self._find_cards(driver)
        print(f"  [Indeed] Found {len(cards)} job cards")

        job_keys: list[str] = []
        seen: set[str] = set()
        for card in cards:
            job_key = self._card_job_key(card)
            if not job_key or job_key in seen:
                continue
            seen.add(job_key)
            job_keys.append(job_key)

        jobs: list[dict[str, Any]] = []
        for idx, job_key in enumerate(job_keys):
            try:
                driver.get(self._url_with_vjk(url, job_key))
                self.sleep(2)
                self.wait_for_human_verification(driver)

                detail_text = self._read_detail_text(driver)
                attrs = extract_attributes(detail_text, attributes)

                title = self._read_detail_title(driver)
                if title and "Job Title" in attrs:
                    attrs["Job Title"] = title

                job_url = f"https://www.indeed.com/viewjob?jk={job_key}"
                jobs.append({"job_url": job_url, "attributes": attrs})
                print(f"    [{idx + 1}] {attrs.get('Job Title', '?')}")

            except Exception as exc:
                print(f"    [Indeed] Error on job {idx + 1}: {exc}")

        return jobs
