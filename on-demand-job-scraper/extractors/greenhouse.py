"""
extractors/greenhouse.py — Extractor for a Greenhouse job posting page
(boards.greenhouse.io / job-boards.greenhouse.io / my.greenhouse.io/.../jobs/<id>).

Greenhouse boards commonly embed schema.org JobPosting JSON-LD directly; the
CSS selectors below are a fallback for boards that don't.
"""

from typing import Any

from bs4 import BeautifulSoup

from extractors.base import apply_overrides, extract_attributes, extract_jsonld_jobposting, html_to_text

TITLE_SELECTORS = ["h1.app-title", "h1"]
LOCATION_SELECTORS = ["div.location", "span.location"]
DESCRIPTION_SELECTORS = ["div#content", "div.content", "section#application", "div[class*='description']"]


def _text(soup: BeautifulSoup, selectors: list[str]) -> str:
    for sel in selectors:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return el.get_text(strip=True)
    return ""


def parse(url: str, html: str, attributes: list[str]) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    jsonld = extract_jsonld_jobposting(html)

    description_el = None
    for sel in DESCRIPTION_SELECTORS:
        description_el = soup.select_one(sel)
        if description_el:
            break
    description = description_el.get_text("\n") if description_el else (jsonld.get("description") or html_to_text(html))

    attrs = extract_attributes(description, attributes)

    apply_overrides(attrs, {
        "title": _text(soup, TITLE_SELECTORS) or jsonld.get("title", ""),
        "company": jsonld.get("company", ""),
        "location": _text(soup, LOCATION_SELECTORS) or jsonld.get("location", ""),
        "salary": jsonld.get("salary", ""),
    })

    return {"job_url": url, "attributes": attrs, "source": "Greenhouse (predefined)"}
