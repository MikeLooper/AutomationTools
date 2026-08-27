"""
extractors/base.py — Shared attribute-extraction helpers for site extractors.

Extraction is HTML-based (BeautifulSoup), not Selenium-based: the page has
already been fetched (either from the live, logged-in browser session or a
plain HTTP request) by page_fetcher.py before any extractor ever sees it.
"""

import json
import re
from typing import Any

from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Discovery/reporting aliases (same file format as job-search-python)
# ---------------------------------------------------------------------------

DEFAULT_LANGUAGE_ALIASES: list[tuple[str, str]] = [
    (".NET", ".NET"), ("C#", "C#"), ("C++", "C++"), ("Java", "Java"),
    ("Python", "Python"), ("Go", "Go"), ("Rust", "Rust"),
    ("TypeScript", "TypeScript"), ("JavaScript", "JavaScript"), ("Ruby", "Ruby"),
]

_LANGUAGE_ALIASES: list[tuple[str, str]] = DEFAULT_LANGUAGE_ALIASES.copy()
_TOOL_ALIASES: list[tuple[str, str]] = []
_JOB_TYPE_ALIASES: list[tuple[str, str]] = []


def configure_extraction_aliases(
    language_aliases: list[tuple[str, str]] | None,
    tool_aliases: list[tuple[str, str]] | None,
    job_type_aliases: list[tuple[str, str]] | None = None,
) -> None:
    """Configure discovery/reporting aliases loaded from settings files."""
    global _LANGUAGE_ALIASES, _TOOL_ALIASES, _JOB_TYPE_ALIASES
    _LANGUAGE_ALIASES = language_aliases.copy() if language_aliases else DEFAULT_LANGUAGE_ALIASES.copy()
    _TOOL_ALIASES = tool_aliases.copy() if tool_aliases else []
    _JOB_TYPE_ALIASES = job_type_aliases.copy() if job_type_aliases else []


def _term_regex(term: str) -> str:
    escaped = re.escape(term)
    if re.fullmatch(r"[A-Za-z0-9_]+", term):
        return rf"\b{escaped}\b"
    return rf"(?<!\w){escaped}(?!\w)"


def _extract_alias_values(text: str, aliases: list[tuple[str, str]]) -> str:
    found: list[str] = []
    seen: set[str] = set()
    for discovery, reporting in aliases:
        if not discovery or not reporting:
            continue
        if re.search(_term_regex(discovery), text, re.IGNORECASE):
            key = reporting.lower()
            if key not in seen:
                seen.add(key)
                found.append(reporting)
    return ", ".join(found)


def extract_programming_languages(text: str) -> str:
    return _extract_alias_values(text, _LANGUAGE_ALIASES)


def extract_tools(text: str) -> str:
    return _extract_alias_values(text, _TOOL_ALIASES)


def extract_job_type(text: str) -> str:
    return _extract_alias_values(text, _JOB_TYPE_ALIASES)


# ---------------------------------------------------------------------------
# Free-text heuristics (used when structured data isn't available)
# ---------------------------------------------------------------------------

US_STATE_CODES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|"
    "MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"
)


# Labeled-field patterns require a colon and a line start, not just trailing
# whitespace: "Location" (and similarly "Role"/"Position") show up constantly
# in ordinary prose — pay-disclosure or EEO boilerplate is full of them — so
# matching on whitespace alone grabs the middle of an unrelated sentence.
# Anchoring to "^Label:" is what a real field line actually looks like.
TITLE_PATTERNS = [r"(?im:^\s*(?:Job\s+Title|Position|Role)\s*:\s*([^\n|]+))"]
COMPANY_PATTERNS = [
    r"(?im:^\s*(?:Company|Employer|Organization)\s*:\s*([^\n|,]{2,80}))",
    r"\bat\s+([A-Z][\w&.,'\-]*(?:\s+[A-Z][\w&.,'\-]*){0,4})\s*(?:\n|-|–|\|)",
]
LOCATION_PATTERNS = [
    r"(?im:^\s*Location\s*:\s*([^\n|]{2,80}))",
    rf"\b([A-Z][a-zA-Z. ]+,\s*(?:{US_STATE_CODES})\b(?:\s*\d{{5}})?)",
    r"\b(Remote(?:\s*[-,]\s*[A-Za-z ]+)?)\b",
]
# A dollar figure's digits, requiring the match to start and end on an
# actual digit (only commas *between* digits count as thousands separators).
# Plain `[\d,]+` would happily swallow a trailing comma that's really just
# sentence punctuation, e.g. "...is $160,000, depending" giving "$160,000,".
_MONEY_DIGITS = r"\d(?:[\d,]*\d)?"

# A full dollar figure, e.g. "$140,000", "$76.5K".
_MONEY_FIGURE = rf"\${_MONEY_DIGITS}(?:\.\d+)?[kK]?"

# An optional "/yr", "/hr", "per year", etc. rate suffix directly attached to
# a figure, as in "$76.5K/yr - $134.9K/yr" or "$30/hr - $50/hr". Without
# this, the range separator match below fails to reach past the suffix, so
# the whole pattern misses a range whose bounds each carry one.
_RATE_SUFFIX = r"(?:\s*(?:/|per\s+)\s*(?:yr|hr|mo|hour|year|month))?"

SALARY_PATTERNS = [
    rf"{_MONEY_FIGURE}{_RATE_SUFFIX}\s*(?:to|-|–|—)\s*{_MONEY_FIGURE}{_RATE_SUFFIX}",
    r"\b\d{2,3}[kK]\s*(?:to|-|–|—)\s*\d{2,3}[kK]\b",
    # A bare thousands-separated range with no "$", e.g. "167,200-209,000" or
    # "151,000.00 - 204,300.00" — some postings state pay this way instead of
    # with a currency symbol. Requires at least one comma group per side so
    # it doesn't fire on unrelated small numbers.
    r"\b\d{1,3}(?:,\d{3}){1,3}(?:\.\d{2})?\s*(?:to|-|–|—)\s*\d{1,3}(?:,\d{3}){1,3}(?:\.\d{2})?\b",
    r"\$[\d,]{6,}\s*(?:to|-|–|—)\s*\$[\d,]{6,}",
    rf"(?i:Up\s+to)\s+{_MONEY_FIGURE}{_RATE_SUFFIX}",
    rf"{_MONEY_FIGURE}{_RATE_SUFFIX}\s*\+",
    rf"(?i:Salary)[:\s]+({_MONEY_FIGURE}{_RATE_SUFFIX}(?:\s*(?:to|-|–)\s*{_MONEY_FIGURE}{_RATE_SUFFIX})?)",
]

# Fallback for a "Salary:" field whose value is a full descriptive sentence
# (e.g. "Salary: $100,000-$140,000 annually, depending on experience")
# rather than a bare numeric range — SALARY_PATTERNS above finds the range
# but drops everything after it. The label and its colon can also land on
# separate lines once run through get_text("\n") if they were originally two
# sibling elements (e.g. a <dt>Salary</dt><dd>: ...</dd> pair), hence the
# optional "\n?" between them. Only tried when SALARY_PATTERNS finds nothing.
LABELED_SALARY_SENTENCE_PATTERN = r"(?im:^[ \t]*Salary[ \t]*\n?[ \t]*:[ \t]*([^\n]{3,150}))"


def _first_match(text: str, patterns: list[str]) -> str:
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1 if m.groups() else 0).strip()
    return ""


def extract_job_title(text: str) -> str:
    for pat in TITLE_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return ""


def extract_company(text: str) -> str:
    return _first_match(text, COMPANY_PATTERNS)


def extract_location(text: str) -> str:
    return _first_match(text, LOCATION_PATTERNS)


def extract_salary(text: str) -> str:
    return _first_match(text, SALARY_PATTERNS)


def extract_labeled_salary_sentence(text: str) -> str:
    """See LABELED_SALARY_SENTENCE_PATTERN. Call only as a fallback when
    extract_salary() finds nothing."""
    match = re.search(LABELED_SALARY_SENTENCE_PATTERN, text)
    return match.group(1).strip() if match else ""


def extract_attributes(text: str, attribute_names: list[str]) -> dict[str, str]:
    """Dispatch to individual extractors for each requested attribute."""
    result: dict[str, str] = {}
    for attr in attribute_names:
        attr_lower = attr.lower()
        if "title" in attr_lower:
            result[attr] = extract_job_title(text)
        elif "compan" in attr_lower or "employer" in attr_lower:
            result[attr] = extract_company(text)
        elif "location" in attr_lower:
            result[attr] = extract_location(text)
        elif "language" in attr_lower or "programming" in attr_lower:
            result[attr] = extract_programming_languages(text)
        elif "tool" in attr_lower:
            result[attr] = extract_tools(text)
        elif "type" in attr_lower:
            result[attr] = extract_job_type(text)
        elif "salary" in attr_lower or "range" in attr_lower:
            result[attr] = extract_salary(text)
        else:
            result[attr] = ""
    return result


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def html_to_text(html: str) -> str:
    """Render HTML down to visible text, similar to a Selenium element's .text."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "title"]):
        tag.decompose()
    return soup.get_text("\n")


def find_section_text(soup: BeautifulSoup, heading_text: str, min_extra_chars: int = 100, max_levels: int = 8) -> str:
    """
    Find a heading (any tag) whose text matches `heading_text` and return the
    text of the section it introduces.

    Sites that build their markup with hashed/generated CSS class names (no
    stable selectors to hook into) still tend to keep human-readable section
    headings, so this climbs from the heading through ancestors until the
    accumulated text grows meaningfully past the heading alone — i.e. until
    the section's body has been pulled in — then returns that, with the
    heading itself stripped off the front.
    """
    heading = None
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "strong", "span", "div"]):
        if tag.get_text(strip=True).casefold() == heading_text.casefold():
            heading = tag
            break
    if heading is None:
        return ""

    baseline = len(heading.get_text(strip=True))
    node = heading
    for _ in range(max_levels):
        parent = node.parent
        if parent is None:
            break
        text = parent.get_text("\n", strip=True)
        if len(text) >= baseline + min_extra_chars:
            if text.casefold().startswith(heading_text.casefold()):
                text = text[len(heading_text):].strip()
            return text
        node = parent
    return ""


def _flatten_jsonld(node: Any) -> list[dict]:
    """Recursively collect dict nodes out of a parsed JSON-LD payload."""
    found: list[dict] = []
    if isinstance(node, dict):
        found.append(node)
        for value in node.values():
            found.extend(_flatten_jsonld(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_flatten_jsonld(item))
    return found


def _salary_from_jsonld(node: dict) -> str:
    salary = node.get("baseSalary")
    if not isinstance(salary, dict):
        return ""
    value = salary.get("value")
    if not isinstance(value, dict):
        return ""
    currency = salary.get("currency", "") or ""
    unit = value.get("unitText", "")
    min_v, max_v = value.get("minValue"), value.get("maxValue")
    if min_v and max_v:
        return f"{currency}{min_v}-{currency}{max_v}{(' /' + unit) if unit else ''}".strip()
    single = value.get("value")
    if single:
        return f"{currency}{single}{(' /' + unit) if unit else ''}".strip()
    return ""


def _location_from_jsonld(node: dict) -> str:
    loc = node.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if not isinstance(loc, dict):
        return ""
    address = loc.get("address")
    if not isinstance(address, dict):
        return ""
    city = address.get("addressLocality", "")
    region = address.get("addressRegion", "")
    parts = [p for p in (city, region) if p]
    return ", ".join(parts)


def extract_jsonld_jobposting(html: str) -> dict[str, str]:
    """
    Look for a schema.org JobPosting block embedded as JSON-LD.
    Many ATS-hosted job pages (Greenhouse, Lever, and even public LinkedIn job
    view pages) emit this for SEO, so it's often available without needing an
    authenticated session at all.
    Returns {} if no JobPosting block is found.
    """
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw or "JobPosting" not in raw:
            continue
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _flatten_jsonld(parsed):
            if node.get("@type") != "JobPosting":
                continue
            description_html = node.get("description", "") or ""
            description_text = BeautifulSoup(description_html, "lxml").get_text("\n") \
                if "<" in description_html else description_html
            org = node.get("hiringOrganization")
            company = org.get("name", "") if isinstance(org, dict) else (org or "")
            return {
                "title": node.get("title", "") or "",
                "company": company or "",
                "location": _location_from_jsonld(node),
                "salary": _salary_from_jsonld(node),
                "employment_type": node.get("employmentType", "") or "",
                "date_posted": node.get("datePosted", "") or "",
                "description": description_text.strip(),
            }
    return {}


def apply_overrides(attrs: dict[str, str], overrides: dict[str, str], only_if_missing: bool = False) -> None:
    """
    Fill in `attrs` (keyed by whatever attribute names the user configured,
    e.g. "Job Title") from `overrides` (keyed by canonical field names, e.g.
    "title") whenever a canonical key name is found inside an attribute name
    and a non-empty override value is available.

    With `only_if_missing=True`, an attribute that already has a value is
    left alone. Useful for fields like location/salary where the page's own
    description text (already run through the shared regex heuristics before
    this is called) is often more specific than a structural guess — e.g. an
    explicit "Location: Remote - US only" line beats inferring a bare country
    name from page chrome.
    """
    for attr in attrs:
        if only_if_missing and attrs[attr]:
            continue
        attr_lower = attr.lower()
        for key, value in overrides.items():
            if value and key in attr_lower:
                attrs[attr] = value
