"""
extractors/indeed.py — Extractor for an Indeed job page: either a direct
job-view page (https://www.indeed.com/viewjob?jk=<id>) or a search-results
page with a job open in the preview pane
(https://www.indeed.com/jobs?q=...&l=...&vjk=<id>), which is how most people
actually browse Indeed's results.

Indeed returns a 403/challenge response to a plain, unauthenticated HTTP
request (confirmed by testing) even for public search results, so this
extractor is really only reachable through the live-browser-attach session
(see README) reading the exact, already-rendered tab.

Indeed renders the preview pane with mostly hashed/atomized CSS classes
(e.g. "css-146c3p1 r-1xnzce8") that carry no meaning and aren't stable, but
a handful of `data-testid` landmarks around it are (confirmed against a
live-captured page): "vj-job-title" for the title, "company-info-metadata"
for the company/rating/location row, "jobDetailsSection" for the pay/job-
type chips, and "vj-job-description-heading" right before the description
body (itself in a plainly-named `simple-job-description-html` div — no
schema.org JSON-LD was present on the page tested). Location and salary sit
in that metadata as bare, unlabeled text, so the shared regex heuristics are
run scoped to just those small containers rather than trusting an exact
selector for them, same approach used for LinkedIn's job-insight pills.

There's also a card list of *other* search results sharing some of the same
generic testids (e.g. "company-name") elsewhere on the page — this is why
title/company/location are all deliberately scoped under the viewjob pane's
own landmarks instead of a bare `[data-testid="company-name"]` lookup, which
would just as happily match the first result card instead of the previewed
job. Some layouts have no "jobDetailsSection" and put the pay/job-type chips
in a "structured-job-summary" block instead, so both are checked.

`parse_card` reads one of those left-hand result cards on its own (title,
company, location, salary snippet, job-type chips — all under stable
`data-testid`s or Indeed's long-lived `jcs-JobTitle` link class). The list
scraper uses it to fill in anything the detail pane didn't yield, or as the
whole result when a card's detail pane never loaded.
"""

from typing import Any

from bs4 import BeautifulSoup

from extractors.base import (
    apply_overrides,
    extract_attributes,
    extract_job_type,
    extract_jsonld_jobposting,
    extract_location,
    extract_salary_range,
    html_to_text,
)

BLOCK_MARKERS = [
    "additional verification required",
    "verify you are a human",
    "pardon our interruption",
    "px-captcha",
]


def _text(soup: BeautifulSoup, selectors: list[str]) -> str:
    for sel in selectors:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return el.get_text(strip=True)
    return ""


def parse(url: str, html: str, attributes: list[str]) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    jsonld = extract_jsonld_jobposting(html)

    description_el = soup.select_one("div.simple-job-description-html")
    description = description_el.get_text("\n") if description_el else (jsonld.get("description") or html_to_text(html))

    attrs = extract_attributes(description, attributes)

    meta_el = soup.select_one("[data-testid='company-info-metadata']")
    meta_text = meta_el.get_text(" ", strip=True) if meta_el else ""
    company_link = meta_el.select_one("a[href*='/cmp/']") if meta_el else None

    details_el = soup.select_one("[data-testid='jobDetailsSection'], [data-testid='structured-job-summary']")
    details_text = details_el.get_text(" ", strip=True) if details_el else ""

    apply_overrides(attrs, {
        "title": _text(soup, ["[data-testid='vj-job-title']"]) or jsonld.get("title", ""),
        "company": (company_link.get_text(strip=True) if company_link else "") or jsonld.get("company", ""),
        "location": extract_location(meta_text) or jsonld.get("location", ""),
        "salary": extract_salary_range(details_text) or jsonld.get("salary", ""),
        "type": extract_job_type(details_text),
    })

    note = None
    lowered = html.lower()
    if any(marker in lowered for marker in BLOCK_MARKERS):
        note = "Indeed showed a bot-verification page instead of the job; only the live-browser-attach session (see README) reliably gets past this."

    return {"job_url": url, "attributes": attrs, "source": "Indeed (predefined)", "note": note}


def card_fields(card_html: str) -> dict[str, str]:
    """Canonical-keyed fields (see `apply_overrides`) read from one result card."""
    soup = BeautifulSoup(card_html, "lxml")
    title_el = soup.select_one("a.jcs-JobTitle span[title]") or soup.select_one("a.jcs-JobTitle")
    salary_el = soup.select_one("[data-testid*='salary-snippet-container']")
    snippets_text = " ".join(el.get_text(" ", strip=True) for el in soup.select("[data-testid*='attribute_snippet_testid']"))
    return {
        "title": (title_el.get("title") or title_el.get_text(strip=True)) if title_el else "",
        "company": _text(soup, ["[data-testid='company-name']"]),
        "location": _text(soup, ["[data-testid='text-location']"]),
        "salary": extract_salary_range(salary_el.get_text(" ", strip=True)) if salary_el else "",
        "type": extract_job_type(snippets_text),
    }


def parse_card(url: str, card_html: str, attributes: list[str]) -> dict[str, Any]:
    """A result built from a result card alone, for when its detail pane never loaded."""
    attrs = extract_attributes(html_to_text(card_html), attributes)
    apply_overrides(attrs, card_fields(card_html))
    return {
        "job_url": url,
        "attributes": attrs,
        "source": "Indeed (predefined)",
        "note": "Only the result card's summary could be read; the full job description didn't load.",
    }
