"""
extractors/linkedin.py — Extractor for LinkedIn job search results.

LinkedIn requires authentication for full job descriptions.
The extractor attempts to work with publicly visible content; if a login
wall appears it skips to the next card and logs a warning.
"""

import time
from typing import Any

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from extractors.base import BaseExtractor, extract_attributes


class LinkedInExtractor(BaseExtractor):
    # Must be non-headless; LinkedIn blocks headless Chrome aggressively.
    HEADLESS = False

    def _extract(
        self,
        driver: webdriver.Chrome,
        url: str,
        attributes: list[str],
    ) -> list[dict[str, Any]]:
        driver.get(url)
        self.sleep(5)

        jobs: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        # LinkedIn job cards sit in <li> elements with a data-occludable-job-id attr
        card_selector = "li[data-occludable-job-id]"

        try:
            self.wait(driver, timeout=20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, card_selector))
            )
        except Exception:
            print("  [LinkedIn] No job cards found — may need authentication.")
            return jobs

        cards = driver.find_elements(By.CSS_SELECTOR, card_selector)
        print(f"  [LinkedIn] Found {len(cards)} job cards")

        for idx, card in enumerate(cards):
            job_id = card.get_attribute("data-occludable-job-id") or ""
            if job_id in seen_ids:
                continue
            if job_id:
                seen_ids.add(job_id)

            try:
                driver.execute_script("arguments[0].scrollIntoView(true);", card)
                card.click()
                self.sleep(3)

                # Build the canonical job URL
                job_url = f"https://www.linkedin.com/jobs/view/{job_id}" if job_id else driver.current_url

                # Check for login wall
                if "authwall" in driver.current_url or "login" in driver.current_url:
                    print(f"    [LinkedIn] Login wall encountered at card {idx+1} — skipping")
                    continue

                detail_text = ""
                for sel in [
                    "div.jobs-description__content",
                    "div[class*='job-view-layout']",
                    "article",
                    "div.description__text",
                ]:
                    try:
                        panel = driver.find_element(By.CSS_SELECTOR, sel)
                        detail_text = panel.text
                        break
                    except Exception:
                        pass

                title = ""
                for sel in [
                    "h1.jobs-unified-top-card__job-title",
                    "h1.top-card-layout__title",
                    "h1",
                ]:
                    try:
                        el = driver.find_element(By.CSS_SELECTOR, sel)
                        title = el.text.strip()
                        if title:
                            break
                    except Exception:
                        pass

                attrs = extract_attributes(detail_text, attributes)
                if title and "Job Title" in attrs:
                    attrs["Job Title"] = title

                jobs.append({"job_url": job_url, "attributes": attrs})
                print(f"    [{idx+1}] {attrs.get('Job Title','?')}")

            except Exception as exc:
                print(f"    [LinkedIn] Error on card {idx+1}: {exc}")

        return jobs
