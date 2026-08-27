"""
extractors/linkedin.py — Extractor for a LinkedIn job page: either a direct
job-view page (https://www.linkedin.com/jobs/view/<id>) or a search-results
page with a job open in the preview pane
(https://www.linkedin.com/jobs/search-results/?currentJobId=<id>), which is
how most people actually browse LinkedIn jobs.

LinkedIn's markup uses hashed, build-generated CSS class names that change
across deploys and A/B tests, so there's nothing stable to select on there.
Instead this reads signals that stay stable because they matter for SEO and
accessibility rather than styling:
  - The <title> tag, which LinkedIn renders as "{Job Title} | {Company} | LinkedIn".
  - An aria-label of the form "Company, {Name}." next to the company logo.
  - The "About the job" heading, whose enclosing section holds the full
    description (found by extract.base.find_section_text).
  - schema.org JobPosting JSON-LD, when LinkedIn includes it (mainly on
    public, logged-out job-view pages), tried first since it's the most
    reliable source when present.
"""

import re
from typing import Any

from bs4 import BeautifulSoup

from extractors.base import (
    apply_overrides,
    extract_attributes,
    extract_jsonld_jobposting,
    extract_labeled_salary_sentence,
    extract_salary,
    find_section_text,
    html_to_text,
)

TITLE_TAG_PATTERN = re.compile(r"^(.*?)\s*\|\s*(.*?)\s*\|\s*LinkedIn\s*$")
COMPANY_ARIA_PATTERN = re.compile(r"^Company,\s*(.+?)\.?$", re.IGNORECASE)


def _title_and_company_from_title_tag(soup: BeautifulSoup) -> tuple[str, str]:
    """
    Only reliable on the signed-in/authenticated page, which consistently
    uses "{Job Title} | {Company} | LinkedIn". The signed-out/anonymous
    server-rendered page's <title> format isn't stable enough to pattern-
    match at all — the exact same posting was observed to render as both
    "{Title} at {Company} - {Location} | LinkedIn Jobs" and
    "{Company} hiring {Title} in {Location} | LinkedIn" across two fetches —
    so _title_from_h1 below is the fallback for that case instead.
    """
    if not soup.title or not soup.title.string:
        return "", ""
    match = TITLE_TAG_PATTERN.match(soup.title.string.strip())
    if not match:
        return "", ""
    return match.group(1).strip(), match.group(2).strip()


def _title_from_h1(soup: BeautifulSoup) -> str:
    """The anonymous server-rendered page reliably puts just the job title in
    an <h1> (the authenticated SPA doesn't use <h1> here at all, so this is
    purely a fallback for when the title-tag parse above comes up empty)."""
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else ""


def _company_from_aria_label(soup: BeautifulSoup) -> str:
    for el in soup.find_all(attrs={"aria-label": True}):
        match = COMPANY_ARIA_PATTERN.match(el["aria-label"].strip())
        if match:
            return match.group(1).strip()
    return ""


def _backup_search_scope(full_text: str, description: str) -> str:
    """
    Salary is sometimes shown in the page's top-card metadata line (e.g.
    "Denver, CO | onsite once a month | $150,000-$180,000"), which sits
    *before* the "About the job" heading and so falls outside `description`'s
    scope entirely. Extending the scope to everything from the top of the
    page through the end of the description picks that up, while still
    excluding whatever trails the description (related-jobs sidebars,
    footers) — the likeliest source of an unrelated dollar figure winning
    just by appearing first in a whole-page search.
    """
    if not description:
        return full_text
    end = full_text.find(description)
    return full_text[: end + len(description)] if end != -1 else full_text


def _location_near(text: str, title: str, company: str) -> str:
    """
    LinkedIn's job header renders as "{Company} {Title} {Location} · {posted} · ...".
    With title/company already known from more reliable signals, they make a
    good anchor to pull location out of that line without needing a selector.
    """
    if not title or not company:
        return ""
    pattern = re.escape(company) + r"\s+" + re.escape(title) + r"\s+([^·|\n]{2,60})\s*(?:·|\|)"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def parse(url: str, html: str, attributes: list[str]) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    jsonld = extract_jsonld_jobposting(html)

    title_tag_title, title_tag_company = _title_and_company_from_title_tag(soup)
    company = _company_from_aria_label(soup) or title_tag_company or jsonld.get("company", "")
    title = title_tag_title or _title_from_h1(soup) or jsonld.get("title", "")

    full_text = html_to_text(html)
    description = find_section_text(soup, "About the job") or jsonld.get("description") or full_text
    attrs = extract_attributes(description, attributes)

    # Title/company from page chrome are more reliable than the naive
    # first-line/regex heuristics extract_attributes just ran, so they win
    # outright. Location/salary are the opposite: the description itself
    # (already checked above) often states them explicitly and more
    # precisely than a structural guess can, so those only fill gaps.
    apply_overrides(attrs, {"title": title, "company": company})

    backup_scope = _backup_search_scope(full_text, description)
    apply_overrides(attrs, {
        "location": jsonld.get("location", "") or _location_near(full_text, title, company),
        # extract_attributes() above already tried the general SALARY_PATTERNS
        # and extract_labeled_salary_sentence() against `description` alone.
        # If that's still empty, widen the search to `backup_scope`: LinkedIn
        # sometimes states salary in the top-card metadata line, which sits
        # before the "About the job" heading and outside `description`'s
        # scope entirely.
        "salary": (
            jsonld.get("salary", "")
            or extract_labeled_salary_sentence(description)
            or extract_salary(backup_scope)
            or extract_labeled_salary_sentence(backup_scope)
        ),
    }, only_if_missing=True)

    note = None
    lowered = html.lower()
    if "authwall" in lowered or "join now to see" in lowered:
        note = "LinkedIn showed a login wall; only publicly visible fields could be extracted."

    return {"job_url": url, "attributes": attrs, "source": "LinkedIn (predefined)", "note": note}
