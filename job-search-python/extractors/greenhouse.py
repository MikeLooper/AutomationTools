"""
extractors/greenhouse.py — Extractor for my.greenhouse.io job boards.

Greenhouse boards list jobs as anchor links; each link leads to a full JD page.
The extractor collects all job links from the listing page, then visits each one.
"""

import re
import requests
from typing import Any

from extractors.base import BaseExtractor, extract_attributes

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}


class GreenhouseExtractor(BaseExtractor):
    HEADLESS = True

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
            print(f"  [Greenhouse] HTTP fetch failed: {exc}")
            return []

        # my.greenhouse.io serves a search shell. If there are public result links in the
        # returned HTML, use them; otherwise this specific search currently has no results.
        job_links = []
        for href in set(
            re.findall(r'href=[\'"]([^\'"]+/jobs/\d+[^\'"]*)[\'"]', resp.text)
        ):
            if href.startswith("http"):
                job_links.append(href)

        print(f"  [Greenhouse] Found {len(job_links)} job links (static)")
        if not job_links:
            return []

        jobs: list[dict[str, Any]] = []
        for idx, job_url in enumerate(job_links):
            try:
                job_resp = requests.get(job_url, headers=HEADERS, timeout=30)
                job_resp.raise_for_status()
                detail_text = job_resp.text

                title_match = re.search(r"<h1[^>]*>(.*?)</h1>", job_resp.text, re.IGNORECASE | re.DOTALL)
                title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip() if title_match else ""

                attrs = extract_attributes(detail_text, attributes)
                if title and "Job Title" in attrs:
                    attrs["Job Title"] = title

                jobs.append({"job_url": job_url, "attributes": attrs})
                print(f"    [{idx+1}] {attrs.get('Job Title', '?')}")
            except Exception as exc:
                print(f"    [Greenhouse] Error on job {idx+1}: {exc}")

        return jobs

    def _extract(
        self,
        driver,
        url: str,
        attributes: list[str],
    ) -> list[dict[str, Any]]:
        from selenium.webdriver.common.by import By

        driver.get(url)
        self.sleep(4)

        jobs: list[dict[str, Any]] = []

        # Greenhouse job boards list jobs inside <div class="opening"> <a href="...">
        # or inside a table with class "jobs-table".
        link_selectors = [
            "div.opening > a",
            "table.jobs-table a",
            "a.job-post-link",
            "li.job-post a",
        ]

        job_links: list[str] = []
        for sel in link_selectors:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                href = el.get_attribute("href") or ""
                if href and href not in job_links:
                    job_links.append(href)
            if job_links:
                break

        # Fallback: search for /jobs/<id> pattern links
        if not job_links:
            els = driver.find_elements(By.XPATH, "//a[contains(@href,'/jobs/')]")
            for el in els:
                href = el.get_attribute("href") or ""
                if href and href not in job_links:
                    job_links.append(href)

        print(f"  [Greenhouse] Found {len(job_links)} job links")

        for idx, job_url in enumerate(job_links):
            try:
                driver.get(job_url)
                self.sleep(2)

                detail_text = ""
                for sel in [
                    "div#content",
                    "div.content",
                    "section#application",
                    "div[class*='description']",
                    "body",
                ]:
                    try:
                        panel = driver.find_element(By.CSS_SELECTOR, sel)
                        detail_text = panel.text
                        break
                    except Exception:
                        pass

                title = ""
                for sel in ["h1.app-title", "h1", "title"]:
                    try:
                        el = driver.find_element(By.CSS_SELECTOR, sel)
                        title = el.text.strip() or el.get_attribute("innerText") or ""
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
                print(f"    [Greenhouse] Error on job {idx+1}: {exc}")

        return jobs
