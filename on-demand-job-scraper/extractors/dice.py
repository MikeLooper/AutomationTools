"""
extractors/dice.py — Extractor for a dice.com job detail page
(https://www.dice.com/job-detail/<id>).
"""

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from extractors.base import apply_overrides, extract_attributes, extract_jsonld_jobposting, html_to_text

TITLE_SELECTORS = ["h1[data-cy='jobTitle']", "h1"]
COMPANY_SELECTORS = ["a[data-cy='companyNameLink']", "li[data-cy='companyNameLocation'] a"]
LOCATION_SELECTORS = ["li[data-cy='companyNameLocation']", "span[data-cy='location']"]
DESCRIPTION_SELECTORS = ["div[data-cy='jobDescription']", "div.job-description", "div[class*='description']"]


def _text(soup: BeautifulSoup, selectors: list[str]) -> str:
    for sel in selectors:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return el.get_text(strip=True)
    return ""


def _from_next_data(html: str) -> dict[str, str]:
    """Dice embeds job details in a Next.js __NEXT_DATA__ JSON blob."""
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL
    )
    if not match:
        return {}
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}

    def find_job_dict(node: Any) -> dict | None:
        if isinstance(node, dict):
            if "jobTitle" in node or ("title" in node and "detailsPageUrl" in node):
                return node
            for value in node.values():
                found = find_job_dict(value)
                if found:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = find_job_dict(item)
                if found:
                    return found
        return None

    job = find_job_dict(payload)
    if not job:
        return {}
    return {
        "title": job.get("jobTitle", "") or job.get("title", ""),
        "company": job.get("companyName", "") or job.get("company", ""),
        "location": job.get("jobLocation", {}).get("displayName", "") if isinstance(job.get("jobLocation"), dict) else job.get("location", ""),
        "salary": job.get("salary", "") or job.get("payRate", ""),
    }


def parse(url: str, html: str, attributes: list[str]) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    jsonld = extract_jsonld_jobposting(html)
    next_data = _from_next_data(html)

    description_el = None
    for sel in DESCRIPTION_SELECTORS:
        description_el = soup.select_one(sel)
        if description_el:
            break
    description = description_el.get_text("\n") if description_el else (jsonld.get("description") or html_to_text(html))

    attrs = extract_attributes(description, attributes)

    apply_overrides(attrs, {
        "title": _text(soup, TITLE_SELECTORS) or next_data.get("title", "") or jsonld.get("title", ""),
        "company": _text(soup, COMPANY_SELECTORS) or next_data.get("company", "") or jsonld.get("company", ""),
        "location": _text(soup, LOCATION_SELECTORS) or next_data.get("location", "") or jsonld.get("location", ""),
        "salary": next_data.get("salary", "") or jsonld.get("salary", ""),
    })

    return {"job_url": url, "attributes": attrs, "source": "Dice (predefined)"}
