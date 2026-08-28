"""
extractors/connectingcolorado.py — Extractor for a jobs.connectingcolorado.gov
job detail view.

This state job board almost always sits behind a login for full details, so
the live-browser-attach fetch path (see page_fetcher.py) matters most here.
"""

from typing import Any

from bs4 import BeautifulSoup

from extractors.base import apply_overrides, extract_attributes, html_to_text

TITLE_SELECTORS = ["main h1", "#main h1", "main h2", "#main h2"]
DESCRIPTION_SELECTORS = ["[data-testid*='job-description']", "[class*='job-description']", "#main", "main"]


def _text(soup: BeautifulSoup, selectors: list[str]) -> str:
    for sel in selectors:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return el.get_text(strip=True)
    return ""


def parse(url: str, html: str, attributes: list[str]) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")

    description_el = None
    for sel in DESCRIPTION_SELECTORS:
        description_el = soup.select_one(sel)
        if description_el:
            break
    description = description_el.get_text("\n") if description_el else html_to_text(html)

    attrs = extract_attributes(description, attributes)
    apply_overrides(attrs, {"title": _text(soup, TITLE_SELECTORS)})

    return {"job_url": url, "attributes": attrs, "source": "Connecting Colorado (predefined)"}
