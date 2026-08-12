"""
extractors/dice.py — Extractor for dice.com job search results.

Dice search pages expose job results in Next.js payload fragments embedded in
the HTML. Parsing that data is more reliable than clicking the UI.
"""

import json
import re
from typing import Any
from html import unescape

import requests

from extractors.base import BaseExtractor, extract_attributes

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


class DiceExtractor(BaseExtractor):
    HEADLESS = True

    @staticmethod
    def _collect_text(value: Any) -> list[str]:
        """Flatten nested payload data into searchable text fragments."""
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, (int, float, bool)):
            return [str(value)]
        if isinstance(value, dict):
            parts: list[str] = []
            for item in value.values():
                parts.extend(DiceExtractor._collect_text(item))
            return parts
        if isinstance(value, (list, tuple, set)):
            parts: list[str] = []
            for item in value:
                parts.extend(DiceExtractor._collect_text(item))
            return parts
        return [str(value)]

    @staticmethod
    def _strip_html(text: str) -> str:
        """Convert HTML content to plain text for extraction matching."""
        no_script = re.sub(r"<script[\\s\\S]*?</script>", " ", text, flags=re.IGNORECASE)
        no_style = re.sub(r"<style[\\s\\S]*?</style>", " ", no_script, flags=re.IGNORECASE)
        no_tags = re.sub(r"<[^>]+>", " ", no_style)
        return re.sub(r"\s+", " ", unescape(no_tags)).strip()

    def extract(self, url: str, attributes: list[str]) -> list[dict[str, Any]]:
        jobs = self._static_extract(url, attributes)
        if jobs:
            return jobs
        return super().extract(url, attributes)

    def _static_extract(self, url: str, attributes: list[str]) -> list[dict[str, Any]]:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
        except Exception as exc:
            print(f"  [Dice] HTTP fetch failed: {exc}")
            return []

        jobs_data = []
        for raw in re.findall(r'\{\\?"id\\?":\\?"[^"]+?\\?".*?\\?"detailsPageUrl\\?":\\?"https://www\.dice\.com/job-detail/.*?\}', resp.text):
            normalized = raw.replace('\\"', '"').replace("\\u0026", "&")
            try:
                jobs_data.append(json.loads(normalized))
            except json.JSONDecodeError:
                continue

        if not jobs_data:
            return []

        jobs: list[dict[str, Any]] = []
        print(f"  [Dice] Found {len(jobs_data)} jobs (static)")
        for item in jobs_data:
            detail_text = "\n".join(
                part for part in self._collect_text(item) if part and str(part).strip()
            )
            attrs = extract_attributes(detail_text, attributes)
            if "Job Title" in attrs:
                attrs["Job Title"] = item.get("jobTitle", "") or item.get("title", "")
            if "Salary Range" in attrs and not attrs["Salary Range"]:
                attrs["Salary Range"] = (
                    item.get("salary")
                    or item.get("payRate")
                    or item.get("salaryRange")
                    or ""
                )

            # If aliases aren't present in search-result payload fields, fetch detail page text.
            needs_language = "Programming Language" in attrs and not attrs["Programming Language"]
            needs_tools = "Tools" in attrs and not attrs["Tools"]
            if needs_language or needs_tools:
                job_url = item.get("detailsPageUrl", "")
                if job_url:
                    try:
                        detail_resp = requests.get(job_url, headers=HEADERS, timeout=30)
                        detail_resp.raise_for_status()
                        page_text = self._strip_html(detail_resp.text)
                        page_attrs = extract_attributes(page_text, attributes)
                        if needs_language and page_attrs.get("Programming Language"):
                            attrs["Programming Language"] = page_attrs["Programming Language"]
                        if needs_tools and page_attrs.get("Tools"):
                            attrs["Tools"] = page_attrs["Tools"]
                    except Exception:
                        pass

            jobs.append({
                "job_url": item.get("detailsPageUrl", ""),
                "attributes": attrs,
            })

        return jobs

    def _extract(
        self,
        driver,
        url: str,
        attributes: list[str],
    ) -> list[dict[str, Any]]:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC

        driver.get(url)
        self.sleep(4)

        jobs: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        # Dice wraps each result in a <dhi-search-card> custom element
        # The inner <a> carries the job URL as href.
        card_selector = "dhi-search-card"

        try:
            self.wait(driver).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, card_selector))
            )
        except Exception:
            print("  [Dice] No job cards found — page may require login or CAPTCHA.")
            return jobs

        cards = driver.find_elements(By.CSS_SELECTOR, card_selector)
        print(f"  [Dice] Found {len(cards)} job cards")

        for idx, card in enumerate(cards):
            try:
                # Scroll into view and click
                driver.execute_script("arguments[0].scrollIntoView(true);", card)
                card.click()
                self.sleep(2)

                # Job URL — grab from the detail panel or from the card link
                job_url = ""
                try:
                    link = card.find_element(By.CSS_SELECTOR, "a[href]")
                    job_url = link.get_attribute("href") or ""
                except Exception:
                    pass

                if job_url and job_url in seen_urls:
                    continue
                if job_url:
                    seen_urls.add(job_url)

                # The detail panel is rendered in #detail-panel or similar
                detail_text = ""
                for sel in [
                    "[data-cy='jobDetails']",
                    ".job-details",
                    "#detail-panel",
                    "div[class*='description']",
                ]:
                    try:
                        panel = driver.find_element(By.CSS_SELECTOR, sel)
                        detail_text = panel.text
                        break
                    except Exception:
                        pass

                if not detail_text:
                    detail_text = card.text

                title = ""
                try:
                    title_el = card.find_element(By.CSS_SELECTOR, "a[data-cy='card-title-link']")
                    title = title_el.text.strip()
                except Exception:
                    pass

                attrs = extract_attributes(detail_text, attributes)
                if title and "Job Title" in attrs:
                    attrs["Job Title"] = title

                jobs.append({"job_url": job_url, "attributes": attrs})
                print(f"    [{idx+1}] {attrs.get('Job Title','?')}")

            except Exception as exc:
                print(f"    [Dice] Error on card {idx+1}: {exc}")

        return jobs
