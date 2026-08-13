"""
extractors/topresume.py — Extractor for careerio.topresume.com job search results.

TopResume search pages are heavily JavaScript-driven. This extractor first
attempts a static discovery path (requests + HTML link discovery) and falls
back to Selenium interactions when necessary.
"""

import re
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from extractors.base import BaseExtractor, extract_attributes


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class TopResumeExtractor(BaseExtractor):
    HEADLESS = True
    API_SEARCH_PATH = "https://careerio.topresume.com/api/jobs/v1/search"

    @staticmethod
    def _first_query_value(parsed_query: dict[str, list[str]], key: str) -> str:
        value = parsed_query.get(key, [""])[0]
        return value.strip()

    def _build_api_params_from_url(self, url: str) -> dict[str, str]:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        params: dict[str, str] = {}
        query_term = self._first_query_value(query, "query")
        if query_term:
            params["query"] = query_term

        page = self._first_query_value(query, "page")
        if page:
            params["page"] = page
        params["perPage"] = "20"

        within_days = self._first_query_value(query, "within_n_days")
        if within_days:
            params["within_n_days"] = within_days

        job_type = self._first_query_value(query, "job_type")
        if job_type:
            params["job_type"] = job_type

        radius = self._first_query_value(query, "radius")
        if radius:
            params["radius"] = radius

        location_id = self._first_query_value(query, "location_id")
        if location_id:
            params["location_id"] = location_id

        # TopResume URLs use only_auto_apply_jobs while API expects auto_apply_compatible.
        only_auto_apply = self._first_query_value(query, "only_auto_apply_jobs").lower()
        if only_auto_apply in {"true", "false"}:
            params["auto_apply_compatible"] = only_auto_apply

        return params

    def _fetch_jobs_from_api(self, params: dict[str, str]) -> list[dict[str, Any]]:
        try:
            resp = requests.get(self.API_SEARCH_PATH, params=params, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            jobs = data.get("jobs", [])
            if isinstance(jobs, list):
                return jobs
            return []
        except Exception as exc:
            print(f"  [TopResume] API fetch failed: {exc}")
            return []

    def _extract_from_api(self, url: str, attributes: list[str]) -> list[dict[str, Any]]:
        params = self._build_api_params_from_url(url)
        jobs_payload = self._fetch_jobs_from_api(params)

        # Some URL filters (notably location_id) can be too restrictive for
        # anonymous reads; retry without location_id to mirror visible UI results.
        if not jobs_payload and "location_id" in params:
            relaxed_params = params.copy()
            relaxed_params.pop("location_id", None)
            jobs_payload = self._fetch_jobs_from_api(relaxed_params)
            if jobs_payload:
                print("  [TopResume] API fallback without location_id returned results")

        print(f"  [TopResume] Found {len(jobs_payload)} jobs (api)")
        if not jobs_payload:
            return []

        jobs: list[dict[str, Any]] = []
        for idx, item in enumerate(jobs_payload):
            title = (item.get("job_title") or "").strip()
            job_url = (item.get("url") or url).strip()
            company_name = (item.get("company_name") or "").strip()
            location = (item.get("location") or "").strip()
            description = item.get("description") or item.get("description_with_html_tags") or ""

            # Normalize HTML-rich descriptions into readable text for attribute extraction.
            detail_text = BeautifulSoup(description, "lxml").get_text("\n", strip=True)
            if company_name:
                detail_text = f"{company_name}\n{detail_text}"
            if location:
                detail_text = f"{detail_text}\nLocation: {location}"

            attrs = extract_attributes(detail_text, attributes)
            if title and "Job Title" in attrs:
                attrs["Job Title"] = title

            # Ensure salary data is not lost when API omits explicit salary field.
            if "Salary Range" in attrs and not attrs["Salary Range"]:
                salary_val = item.get("salary")
                if salary_val:
                    attrs["Salary Range"] = str(salary_val)

            jobs.append({"job_url": job_url, "attributes": attrs})
            print(f"    [{idx+1}] {attrs.get('Job Title', '?')}")

        return jobs

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
    def _discover_job_urls_from_html(base_url: str, html: str) -> list[str]:
        host = (urlparse(base_url).hostname or "").lower()
        urls: list[str] = []
        seen: set[str] = set()

        for href in re.findall(r'href=[\"\']([^\"\']+)[\"\']', html, flags=re.IGNORECASE):
            if not href or href.startswith("javascript:"):
                continue
            if not TopResumeExtractor._is_probable_job_link(href):
                continue

            abs_url = TopResumeExtractor._normalize_job_url(base_url, href)
            parsed = urlparse(abs_url)
            if parsed.scheme not in {"http", "https"}:
                continue
            if host and parsed.hostname and not parsed.hostname.lower().endswith(host):
                continue

            clean = abs_url.split("#", 1)[0]
            if clean not in seen:
                seen.add(clean)
                urls.append(clean)

        return urls

    @staticmethod
    def _extract_title_from_soup(soup: BeautifulSoup) -> str:
        for selector in [
            "h1",
            "[data-testid*='title']",
            "[class*='title']",
        ]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(" ", strip=True)
                if text:
                    return text
        title_el = soup.select_one("title")
        return title_el.get_text(" ", strip=True) if title_el else ""

    @staticmethod
    def _extract_text_from_soup(soup: BeautifulSoup) -> str:
        detail_el = (
            soup.select_one("[data-testid*='description']")
            or soup.select_one("[class*='description']")
            or soup.select_one("main")
            or soup.select_one("article")
            or soup.body
        )
        if not detail_el:
            return ""
        return detail_el.get_text("\n", strip=True)

    def extract(self, url: str, attributes: list[str]) -> list[dict[str, Any]]:
        jobs = self._extract_from_api(url, attributes)
        if jobs:
            return jobs

        jobs = self._static_extract(url, attributes)
        if jobs:
            return jobs
        return super().extract(url, attributes)

    def _static_extract(self, url: str, attributes: list[str]) -> list[dict[str, Any]]:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
        except Exception as exc:
            print(f"  [TopResume] HTTP fetch failed: {exc}")
            return []

        job_urls = self._discover_job_urls_from_html(url, resp.text)
        print(f"  [TopResume] Found {len(job_urls)} job links (static)")
        if not job_urls:
            return []

        jobs: list[dict[str, Any]] = []
        for idx, job_url in enumerate(job_urls):
            try:
                job_resp = requests.get(job_url, headers=HEADERS, timeout=30)
                job_resp.raise_for_status()

                soup = BeautifulSoup(job_resp.text, "lxml")
                detail_text = self._extract_text_from_soup(soup)
                title = self._extract_title_from_soup(soup)

                attrs = extract_attributes(detail_text, attributes)
                if title and "Job Title" in attrs:
                    attrs["Job Title"] = title

                jobs.append({"job_url": job_url, "attributes": attrs})
                print(f"    [{idx+1}] {attrs.get('Job Title', '?')}")
            except Exception as exc:
                print(f"    [TopResume] Error on job {idx+1}: {exc}")

        return jobs

    def _extract(
        self,
        driver,
        url: str,
        attributes: list[str],
    ) -> list[dict[str, Any]]:
        from selenium.webdriver.common.by import By

        driver.get(url)
        self.sleep(5)

        # Trigger lazy-loaded content.
        for _ in range(3):
            driver.execute_script("window.scrollBy(0, document.body.scrollHeight * 0.6);")
            self.sleep(1.2)

        page_source = driver.page_source
        discovered_urls = self._discover_job_urls_from_html(url, page_source)

        # Fallback: harvest candidate hrefs directly from DOM anchors.
        if not discovered_urls:
            seen: set[str] = set()
            for link in driver.find_elements(By.CSS_SELECTOR, "a[href]"):
                href = (link.get_attribute("href") or "").strip()
                if not href or not self._is_probable_job_link(href):
                    continue
                abs_url = self._normalize_job_url(url, href).split("#", 1)[0]
                if abs_url not in seen:
                    seen.add(abs_url)
                    discovered_urls.append(abs_url)

        print(f"  [TopResume] Found {len(discovered_urls)} job links (selenium)")
        if not discovered_urls:
            return self._extract_by_clicking_cards(driver, url, attributes)

        jobs: list[dict[str, Any]] = []
        for idx, job_url in enumerate(discovered_urls):
            try:
                driver.get(job_url)
                self.sleep(2)

                title = ""
                for sel in ["h1", "[data-testid*='title']", "[class*='title']"]:
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
                        detail_text = panel.text
                        if detail_text:
                            break
                    except Exception:
                        pass

                attrs = extract_attributes(detail_text, attributes)
                if title and "Job Title" in attrs:
                    attrs["Job Title"] = title

                jobs.append({"job_url": job_url, "attributes": attrs})
                print(f"    [{idx+1}] {attrs.get('Job Title', '?')}")
            except Exception as exc:
                print(f"    [TopResume] Error on job {idx+1}: {exc}")

        return jobs

    def _extract_by_clicking_cards(
        self,
        driver,
        url: str,
        attributes: list[str],
    ) -> list[dict[str, Any]]:
        from selenium.webdriver.common.by import By

        jobs: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

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
            cards = driver.find_elements(By.CSS_SELECTOR, sel)
            if cards:
                break

        print(f"  [TopResume] Found {len(cards)} job cards (click fallback)")
        if not cards:
            return []

        for idx, card in enumerate(cards):
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
                self.sleep(0.8)
                card.click()
                self.sleep(1.8)

                current_url = (driver.current_url or "").strip()
                if not current_url or current_url == url:
                    current_url = self._find_detail_url_near_card(driver, card, url)

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

                title = ""
                for sel in [
                    "h1",
                    "[data-testid*='job-title']",
                    "[data-testid*='title']",
                    "[class*='title']",
                ]:
                    try:
                        el = driver.find_element(By.CSS_SELECTOR, sel)
                        title = (el.text or "").strip()
                        if title:
                            break
                    except Exception:
                        pass

                if not title:
                    try:
                        title = (card.text or "").split("\n", 1)[0].strip()
                    except Exception:
                        title = ""

                attrs = extract_attributes(detail_text, attributes)
                if title and "Job Title" in attrs:
                    attrs["Job Title"] = title

                unique_key = ((current_url or url), title)
                if unique_key in seen:
                    continue
                seen.add(unique_key)

                jobs.append({"job_url": current_url or url, "attributes": attrs})
                print(f"    [{idx+1}] {attrs.get('Job Title', '?')}")
            except Exception as exc:
                print(f"    [TopResume] Error on card {idx+1}: {exc}")

        return jobs

    @staticmethod
    def _find_detail_url_near_card(driver, card, fallback_url: str) -> str:
        from selenium.webdriver.common.by import By

        try:
            link = card.find_element(By.CSS_SELECTOR, "a[href]")
            href = (link.get_attribute("href") or "").strip()
            if href and TopResumeExtractor._is_probable_job_link(href):
                return TopResumeExtractor._normalize_job_url(fallback_url, href)
        except Exception:
            pass

        try:
            for link in driver.find_elements(By.CSS_SELECTOR, "a[href]"):
                href = (link.get_attribute("href") or "").strip()
                if href and TopResumeExtractor._is_probable_job_link(href):
                    return TopResumeExtractor._normalize_job_url(fallback_url, href)
        except Exception:
            pass

        return fallback_url