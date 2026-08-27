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
    extract_job_type,
    extract_jsonld_jobposting,
    extract_labeled_salary_sentence,
    extract_salary,
    extract_salary_range,
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

    Requires a real, located `description` to anchor that end boundary.
    Without one there's nothing to bound the scope by, so this must return
    "" rather than the full page — searching the whole page for a dollar
    figure is exactly the failure mode this function exists to avoid (it
    would just as happily match LinkedIn's own estimated-pay insight badge,
    an applied search-filter chip, or a "Similar jobs" teaser as the real,
    employer-stated salary).
    """
    if not description:
        return ""
    end = full_text.find(description)
    return full_text[: end + len(description)] if end != -1 else ""


def _heading_tag(soup: BeautifulSoup, heading_text: str):
    """Same heading lookup find_section_text uses, exposed as the tag itself."""
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "strong", "span", "div"]):
        if tag.get_text(strip=True).casefold() == heading_text.casefold():
            return tag
    return None


def _job_posting_scope(soup: BeautifulSoup) -> str:
    """
    Job-insight pills (Full-time, On-site, ...) and a "Job details" panel
    (Seniority level, Employment type, ...) can each render either before or
    after the "About the job" body depending on a given posting's layout —
    one job had them in the top card *before* the description, another had
    them in a details panel *after* it. A positional window anchored to the
    description's start or end (like `_backup_search_scope`) only ever
    catches one of those, so it's the wrong tool for job type specifically.

    Instead, find the smallest DOM container that holds *both* the job
    title (<h1>) and the "About the job" heading — i.e. the actual
    job-posting block — and use all of its text regardless of internal
    ordering. A "Similar jobs"/"People also viewed" rail is a structurally
    separate block (not nested with the title and description together), so
    it's excluded by this no matter where it falls in source order.
    """
    title_tag = soup.find("h1")
    about_tag = _heading_tag(soup, "About the job")
    if title_tag is None or about_tag is None:
        return ""
    about_ancestor_ids = {id(parent) for parent in about_tag.parents}
    for ancestor in title_tag.parents:
        if id(ancestor) in about_ancestor_ids:
            return ancestor.get_text("\n", strip=True)
    return ""


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
    section_text = find_section_text(soup, "About the job") or jsonld.get("description", "")
    # Only a genuinely located "About the job" section (or JSON-LD) is safe to
    # run the salary regex against. `full_text` is used below as a fallback
    # for the *other* attributes (title/company/languages/tools all have
    # their own extra signals or are low-risk keyword lookups), but salary
    # must never be searched for in it: extract_salary()/_first_match just
    # return the first pattern match found anywhere in the given text, so
    # feeding it the whole page would let nav chrome, an applied search
    # filter, a "Similar jobs" teaser, or LinkedIn's own estimated-pay
    # insight badge win over the employer's real stated salary purely by
    # appearing earlier on the page.
    description = section_text or full_text
    attrs = extract_attributes(description, attributes)
    if not section_text:
        for attr in attrs:
            if "salary" in attr.lower() or "range" in attr.lower():
                attrs[attr] = ""

    # Title/company from page chrome are more reliable than the naive
    # first-line/regex heuristics extract_attributes just ran, so they win
    # outright. Location/salary are the opposite: the description itself
    # (already checked above) often states them explicitly and more
    # precisely than a structural guess can, so those only fill gaps.
    #
    # Job type ("Full-time", "On-site", "Hybrid", "Remote", ...) is shown
    # either as job-insight pills in the top card (before "About the job")
    # or in a "Job details" panel below the description (after it) —
    # LinkedIn places it differently across postings — so extract_attributes()
    # above, run only against `description`, routinely finds nothing.
    # extract_job_type() just checks whether each known alias term appears
    # anywhere in the given text, with no first-match-wins tie-breaking, so
    # it needs a scope wide enough to reach it on either side — but not the
    # whole page: `full_text` also holds "Similar jobs"/"People also viewed"
    # sidebar teasers for OTHER postings, and a keyword like "Remote"
    # appearing there is as much a false positive as an unrelated dollar
    # figure would be for salary. `_job_posting_scope` (the DOM container
    # shared by the title and the description) reaches both placements while
    # excluding that sibling, other-jobs content; `backup_scope` below is a
    # narrower fallback for when that structural lookup finds nothing.
    backup_scope = _backup_search_scope(full_text, section_text)
    posting_scope = _job_posting_scope(soup) or backup_scope
    apply_overrides(attrs, {"title": title, "company": company, "type": extract_job_type(posting_scope)})

    apply_overrides(attrs, {
        "location": jsonld.get("location", "") or _location_near(full_text, title, company),
    }, only_if_missing=True)

    # Salary is shown as a page-chrome pill just like job type — sometimes
    # in the top card before "About the job", sometimes in a details panel
    # after it — so it needs that same wide `posting_scope` to be found at
    # all. But unlike job type, extract_salary()'s weaker fallback patterns
    # (e.g. "$X+") match *any* incidental dollar figure, so extract_attributes()
    # above can end up setting attrs["Salary Range"] to something wrong from
    # an unrelated mention inside the body (a stipend, a discount, ...)
    # *before* this code ever runs. Gating on "only fill in if still empty"
    # (as the rest of this override does) would then leave that wrong value
    # in place forever, since it's already non-empty. So the high-confidence,
    # two-sided range check runs first and — if it finds a real range in the
    # wider scope — always wins outright over whatever the initial pass
    # guessed. Only when no range exists anywhere do the narrower/weaker
    # signals get a turn, same priority as before.
    salary = (
        jsonld.get("salary", "")
        or extract_salary_range(posting_scope)
        or (extract_labeled_salary_sentence(section_text) if section_text else "")
        or extract_salary(backup_scope)
        or extract_labeled_salary_sentence(backup_scope)
    )
    apply_overrides(attrs, {"salary": salary})

    note = None
    lowered = html.lower()
    if "authwall" in lowered or "join now to see" in lowered:
        note = "LinkedIn showed a login wall; only publicly visible fields could be extracted."

    return {"job_url": url, "attributes": attrs, "source": "LinkedIn (predefined)", "note": note}
