"""
extractors/connectingcolorado.py - Extractor for jobs.connectingcolorado.gov.

This site uses a split layout: job cards on the left and a detail pane on the
right. The extractor clicks each card and reads the updated detail content.
"""

from typing import Any

from selenium import webdriver
from selenium.webdriver.common.by import By

from extractors.base import BaseExtractor, extract_attributes


class ConnectingColoradoExtractor(BaseExtractor):
    HEADLESS = True

    CARD_SELECTORS = [
        ".job-card-external",
        ".job-card-content",
        "[role='option'][aria-label^='Job,']",
        "a[aria-label^='Job,']",
        "li[aria-label^='Job,']",
        "[class*='job-card']",
    ]

    DETAIL_SELECTORS = [
        "[data-testid*='job-description']",
        "[class*='job-description']",
        "[id='main']",
        "main",
    ]

    DETAIL_TITLE_SELECTORS = [
        "main h1",
        "#main h1",
        "main h2",
        "#main h2",
    ]

    @staticmethod
    def _safe_text(el) -> str:
        try:
            return (el.text or "").strip()
        except Exception:
            return ""

    def _find_cards(self, driver: webdriver.Chrome):
        cards = []
        for selector in self.CARD_SELECTORS:
            cards = driver.find_elements(By.CSS_SELECTOR, selector)
            cards = [card for card in cards if self._safe_text(card)]
            if cards:
                return cards

        # Fallback: infer job cards from common left-panel text pattern.
        fallback = driver.find_elements(By.XPATH, "//*[contains(@aria-label,'Job,')]")
        return [card for card in fallback if self._safe_text(card)]

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
            # If the page marks a section with "Job Description", prioritize that.
            node = driver.find_element(
                By.XPATH,
                "//*[contains(normalize-space(.), 'Job Description')]/ancestor::*[self::section or self::article or self::div][1]",
            )
            text = self._safe_text(node)
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

        # Fallback to visible heading near the active detail pane.
        for xpath in [
            "//*[@id='main']//h1[1]",
            "//*[@id='main']//h2[1]",
            "//main//h1[1]",
            "//main//h2[1]",
        ]:
            try:
                el = driver.find_element(By.XPATH, xpath)
                text = self._safe_text(el)
                if text:
                    return text
            except Exception:
                pass
        return ""

    def _read_card_title(self, card) -> str:
        # Prefer link text when the card container includes extra metadata.
        for selector in [
            ".job-card-title",
            "[class*='job-card-title']",
            "a[aria-label^='Job,']",
            "a[href]",
            "h2",
            "h3",
        ]:
            try:
                link = card.find_element(By.CSS_SELECTOR, selector)
                text = self._safe_text(link)
                if text:
                    return text.splitlines()[0].strip()
            except Exception:
                pass

        text = self._safe_text(card)
        if text:
            return text.splitlines()[0].strip()
        return ""

    @staticmethod
    def _clean_title(title: str) -> str:
        value = (title or "").strip()
        if not value:
            return ""

        lowered = value.lower()
        if lowered in {"job", "job,"}:
            return ""

        if lowered.startswith("job,"):
            candidate = value.split(",", 1)[1].strip()
            if candidate:
                return candidate

        return value

    def _extract(
        self,
        driver: webdriver.Chrome,
        url: str,
        attributes: list[str],
    ) -> list[dict[str, Any]]:
        driver.get(url)
        self.sleep(4)

        jobs: list[dict[str, Any]] = []
        seen: set[str] = set()

        cards = self._find_cards(driver)
        print(f"  [ConnectingColorado] Found {len(cards)} job cards")

        if not cards:
            detail_text = self._read_detail_text(driver)
            attrs = extract_attributes(detail_text, attributes)
            jobs.append({"job_url": url, "attributes": attrs})
            return jobs

        total = len(cards)
        for idx in range(total):
            try:
                live_cards = self._find_cards(driver)
                if idx >= len(live_cards):
                    break

                card = live_cards[idx]
                card_title = self._clean_title(self._read_card_title(card))

                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", card)
                try:
                    card.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", card)

                self.sleep(2)

                detail_text = self._read_detail_text(driver)
                attrs = extract_attributes(detail_text, attributes)

                detail_title = self._clean_title(self._read_detail_title(driver))
                title = detail_title or card_title

                if "Job Title" in attrs and title:
                    attrs["Job Title"] = title

                job_url = driver.current_url or url
                identity = job_url if job_url else f"{title}:{idx}"
                if identity in seen:
                    continue
                seen.add(identity)

                jobs.append({"job_url": job_url, "attributes": attrs})
                print(f"    [{idx + 1}] {attrs.get('Job Title', '?')}")

            except Exception as exc:
                print(f"    [ConnectingColorado] Error on card {idx + 1}: {exc}")

        return jobs
