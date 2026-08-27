"""
extractors/generic.py — Fallback extractor for sites with no dedicated module.

Tries schema.org JobPosting JSON-LD first (many job boards embed this for SEO
even when the page itself needs a login to browse), then falls back to plain
text heuristics.
"""

from typing import Any

from bs4 import BeautifulSoup

from extractors.base import apply_overrides, extract_attributes, extract_jsonld_jobposting, html_to_text


def parse(url: str, html: str, attributes: list[str]) -> dict[str, Any]:
    jsonld = extract_jsonld_jobposting(html)
    text = jsonld.get("description") or html_to_text(html)

    attrs = extract_attributes(text, attributes)

    if jsonld:
        apply_overrides(attrs, {
            "title": jsonld.get("title", ""),
            "company": jsonld.get("company", ""),
            "location": jsonld.get("location", ""),
            "salary": jsonld.get("salary", ""),
        })

    empty_title_attrs = [a for a in attrs if "title" in a.lower() and not attrs[a]]
    if empty_title_attrs:
        soup = BeautifulSoup(html, "lxml")
        if soup.title and soup.title.string:
            for attr in empty_title_attrs:
                attrs[attr] = soup.title.string.strip()

    return {"job_url": url, "attributes": attrs, "source": "generic (heuristic extraction)"}
