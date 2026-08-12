"""
extractors/glassdoor.py — Extractor for glassdoor.com job search results.

Glassdoor often presents a sign-in modal.  The extractor attempts to dismiss
it, then clicks each job card to load the full description.
"""

import time
from typing import Any

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from extractors.base import BaseExtractor, extract_attributes


class GlassdoorExtractor(BaseExtractor):
    # Run non-headless so Glassdoor doesn't immediately block with CAPTCHA.
    # Set to True if you have a solved-cookie strategy.
    HEADLESS = False

    def _extract(
        self,
        driver: webdriver.Chrome,
        url: str,
        attributes: list[str],
    ) -> list[dict[str, Any]]:
        driver.get(url)
        self.sleep(5)

        # Dismiss sign-in modal if present
        for close_sel in [
            "button[data-test='job-alert-modal-close']",
            "span.SVGInline.modal_closeIcon",
            "button.modal_closeBtn",
            "[aria-label='Close']",
        ]:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, close_sel)
                btn.click()
                self.sleep(1)
                break
            except Exception:
                pass

        jobs: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        card_selector = "li[data-test='jobListing'], li.react-job-listing"

        try:
            self.wait(driver).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, card_selector))
            )
        except Exception:
            print("  [Glassdoor] No job cards found — may need authentication.")
            return jobs

        cards = driver.find_elements(By.CSS_SELECTOR, card_selector)
        print(f"  [Glassdoor] Found {len(cards)} job cards")

        for idx, card in enumerate(cards):
            try:
                driver.execute_script("arguments[0].scrollIntoView(true);", card)
                card.click()
                self.sleep(3)

                job_url = driver.current_url

                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                detail_text = ""
                for sel in [
                    "[data-test='jobDescriptionContent']",
                    "div.jobDescriptionContent",
                    "div[class*='desc']",
                    "div.desc",
                ]:
                    try:
                        panel = driver.find_element(By.CSS_SELECTOR, sel)
                        detail_text = panel.text
                        break
                    except Exception:
                        pass

                title = ""
                try:
                    title_el = card.find_element(
                        By.CSS_SELECTOR,
                        "[data-test='job-link'], a[class*='jobLink']"
                    )
                    title = title_el.text.strip()
                except Exception:
                    pass

                attrs = extract_attributes(detail_text, attributes)
                if title and "Job Title" in attrs:
                    attrs["Job Title"] = title

                jobs.append({"job_url": job_url, "attributes": attrs})
                print(f"    [{idx+1}] {attrs.get('Job Title','?')}")

            except Exception as exc:
                print(f"    [Glassdoor] Error on card {idx+1}: {exc}")

        return jobs
