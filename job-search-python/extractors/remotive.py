"""
extractors/remotive.py — Extractor for remotive.com job listings.

Remotive search pages expose the results in an embedded JavaScript payload,
which is more reliable than scraping the rendered HTML.
"""

import json
import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from extractors.base import BaseExtractor, extract_attributes, extract_programming_languages, extract_tools

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
BASE_URL = "https://remotive.com"


class RemotiveExtractor(BaseExtractor):
    HEADLESS = True

    @staticmethod
    def _metadata_text(*parts: object) -> str:
        """Join optional metadata parts into one extraction text blob."""
        text_parts: list[str] = []
        for part in parts:
            if part is None:
                continue
            if isinstance(part, list):
                text_parts.extend(str(item) for item in part if item)
            else:
                value = str(part).strip()
                if value:
                    text_parts.append(value)
        return "\n".join(text_parts)

    @staticmethod
    def _populate_missing_remotive_attrs(
        attrs: dict[str, str],
        source_text: str,
    ) -> None:
        """Fill empty language/tool attributes from metadata, then fallback to text."""
        if "Programming Language" in attrs and not attrs["Programming Language"]:
            value = extract_programming_languages(source_text)
            attrs["Programming Language"] = value if value else "Not specified"
        if "Tools" in attrs and not attrs["Tools"]:
            value = extract_tools(source_text)
            attrs["Tools"] = value if value else "Not specified"

    def extract(self, url: str, attributes: list[str]) -> list[dict[str, Any]]:
        """Override to try static scraping first, then fall back to Selenium."""
        jobs, used_fallback = self._static_extract(url, attributes)
        if jobs:
            return jobs
        if not used_fallback:
            return []
        # Fall back to Selenium-based extraction
        return super().extract(url, attributes)

    # ------------------------------------------------------------------
    # Static (requests + BeautifulSoup) path
    # ------------------------------------------------------------------

    def _static_extract(self, url: str, attributes: list[str]) -> tuple[list[dict[str, Any]], bool]:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except Exception as exc:
            print(f"  [Remotive] HTTP fetch failed: {exc}")
            return [], True

        jobs: list[dict[str, Any]] = []
        match = re.search(
            r"window\.__INITIAL_SEARCH_RESULTS__\s*=\s*(\{.*?\});",
            resp.text,
            re.DOTALL,
        )
        if not match:
            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select("li.job-list-item, li[class*='job']")
            print(f"  [Remotive] Found {len(cards)} job cards (static-html)")
            if not cards:
                return [], False

            for card in cards:
                link_el = card.select_one("a[href]")
                if not link_el:
                    continue
                job_path = link_el.get("href", "")
                job_url = urljoin(BASE_URL, job_path)

                try:
                    job_resp = requests.get(job_url, headers=HEADERS, timeout=20)
                    job_resp.raise_for_status()
                    job_soup = BeautifulSoup(job_resp.text, "lxml")

                    detail_el = (
                        job_soup.select_one("div[class*='description']")
                        or job_soup.select_one("div#job-description")
                        or job_soup.select_one("article")
                        or job_soup.body
                    )
                    detail_text = detail_el.get_text(separator="\n") if detail_el else ""

                    title_el = job_soup.select_one("h1")
                    title = title_el.get_text(strip=True) if title_el else ""

                    attrs = extract_attributes(detail_text, attributes)
                    if title and "Job Title" in attrs:
                        attrs["Job Title"] = title

                    fallback_text = self._metadata_text(title, detail_text)
                    self._populate_missing_remotive_attrs(attrs, fallback_text)

                    jobs.append({"job_url": job_url, "attributes": attrs})

                except Exception as exc:
                    print(f"    [Remotive] Error fetching {job_url}: {exc}")

            return jobs, True

        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            return [], False

        hits = payload.get("results", [{}])[0].get("hits", [])
        print(f"  [Remotive] Found {len(hits)} job cards (embedded-data)")
        if not hits:
            return [], False

        for hit in hits:
            job_url = hit.get("url", "")
            if not job_url:
                continue

            # Fetch the individual job page
            try:
                job_resp = requests.get(job_url, headers=HEADERS, timeout=20)
                job_resp.raise_for_status()
                job_soup = BeautifulSoup(job_resp.text, "lxml")

                detail_el = (
                    job_soup.select_one("div[class*='description']")
                    or job_soup.select_one("div#job-description")
                    or job_soup.select_one("article")
                    or job_soup.body
                )
                detail_text = detail_el.get_text(separator="\n") if detail_el else ""

                title_el = job_soup.select_one("h1")
                title = title_el.get_text(strip=True) if title_el else ""

                attrs = extract_attributes(detail_text, attributes)
                if "Job Title" in attrs:
                    attrs["Job Title"] = title or hit.get("title", "")
                if "Programming Language" in attrs and not attrs["Programming Language"]:
                    attrs["Programming Language"] = extract_programming_languages(" ".join(hit.get("skills", [])))
                if "Tools" in attrs and not attrs["Tools"]:
                    attrs["Tools"] = extract_tools(" ".join(hit.get("skills", [])))
                fallback_text = self._metadata_text(
                    title,
                    detail_text,
                    hit.get("title", ""),
                    hit.get("occupation", ""),
                    hit.get("category", ""),
                    hit.get("company_name", ""),
                    hit.get("skills", []),
                )
                self._populate_missing_remotive_attrs(attrs, fallback_text)
                if "Salary Range" in attrs and not attrs["Salary Range"]:
                    attrs["Salary Range"] = hit.get("salary", "")

                jobs.append({"job_url": job_url, "attributes": attrs})

            except Exception as exc:
                print(f"    [Remotive] Error fetching {job_url}: {exc}")

        return jobs, True

    # ------------------------------------------------------------------
    # Selenium fallback
    # ------------------------------------------------------------------

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
        cards = driver.find_elements(By.CSS_SELECTOR, "li.job-list-item, li[class*='job']")
        print(f"  [Remotive/Selenium] Found {len(cards)} job cards")

        job_urls = []
        for card in cards:
            try:
                link = card.find_element(By.CSS_SELECTOR, "a")
                href = link.get_attribute("href") or ""
                if href:
                    job_urls.append(href)
            except Exception:
                pass

        for idx, job_url in enumerate(job_urls):
            try:
                driver.get(job_url)
                self.sleep(2)
                detail_text = driver.find_element(By.TAG_NAME, "body").text
                title_el = driver.find_element(By.CSS_SELECTOR, "h1")
                title = title_el.text.strip() if title_el else ""
                attrs = extract_attributes(detail_text, attributes)
                if title and "Job Title" in attrs:
                    attrs["Job Title"] = title
                fallback_text = self._metadata_text(title, detail_text)
                self._populate_missing_remotive_attrs(attrs, fallback_text)
                jobs.append({"job_url": job_url, "attributes": attrs})
                print(f"    [{idx+1}] {attrs.get('Job Title','?')}")
            except Exception as exc:
                print(f"    [Remotive/Selenium] Error: {exc}")

        return jobs
