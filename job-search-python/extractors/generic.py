"""
extractors/generic.py — Generic Selenium extractor for unrecognised job sites.

Uses heuristics to find job cards and description panels.
"""

from typing import Any

from selenium import webdriver
from selenium.webdriver.common.by import By

from extractors.base import BaseExtractor, extract_attributes


class GenericExtractor(BaseExtractor):
    HEADLESS = True

    # CSS selectors tried in order to find job list items
    CARD_SELECTORS = [
        "li[class*='job']",
        "div[class*='job-card']",
        "article[class*='job']",
        "div[class*='posting']",
    ]

    # CSS selectors tried in order to find the description panel
    DETAIL_SELECTORS = [
        "div[class*='description']",
        "div[class*='details']",
        "article",
        "main",
    ]

    def _extract(
        self,
        driver: webdriver.Chrome,
        url: str,
        attributes: list[str],
    ) -> list[dict[str, Any]]:
        driver.get(url)
        self.sleep(4)

        jobs: list[dict[str, Any]] = []

        cards = []
        for sel in self.CARD_SELECTORS:
            cards = driver.find_elements(By.CSS_SELECTOR, sel)
            if cards:
                break

        print(f"  [Generic] Found {len(cards)} job cards")

        if not cards:
            # Single-page job description — scrape the page directly
            body_text = driver.find_element(By.TAG_NAME, "body").text
            attrs = extract_attributes(body_text, attributes)
            jobs.append({"job_url": url, "attributes": attrs})
            return jobs

        for idx, card in enumerate(cards):
            try:
                driver.execute_script("arguments[0].scrollIntoView(true);", card)
                card.click()
                self.sleep(2)

                job_url = driver.current_url
                detail_text = ""
                for sel in self.DETAIL_SELECTORS:
                    try:
                        panel = driver.find_element(By.CSS_SELECTOR, sel)
                        detail_text = panel.text
                        break
                    except Exception:
                        pass

                if not detail_text:
                    detail_text = card.text

                attrs = extract_attributes(detail_text, attributes)
                jobs.append({"job_url": job_url, "attributes": attrs})
                print(f"    [{idx+1}] {attrs.get('Job Title','?')}")

            except Exception as exc:
                print(f"    [Generic] Error on card {idx+1}: {exc}")

        return jobs
