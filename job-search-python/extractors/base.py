"""
extractors/base.py — Base extractor class and shared attribute-extraction helpers.
"""

import re
import time
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import requests
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


# ---------------------------------------------------------------------------
# Attribute extraction helpers
# ---------------------------------------------------------------------------

# Default aliases used until the runtime settings files are loaded.
DEFAULT_LANGUAGE_ALIASES: list[tuple[str, str]] = [
    (".NET", ".NET"),
    ("C#", "C#"),
    ("C++", "C++"),
    ("Java", "Java"),
    ("Python", "Python"),
    ("Go", "Go"),
    ("Golang", "Golang"),
    ("Rust", "Rust"),
    ("TypeScript", "TypeScript"),
    ("JavaScript", "JavaScript"),
    ("Ruby", "Ruby"),
    ("Scala", "Scala"),
    ("Kotlin", "Kotlin"),
    ("Swift", "Swift"),
    ("PHP", "PHP"),
    ("Perl", "Perl"),
    ("R", "R"),
    ("COBOL", "COBOL"),
    ("F#", "F#"),
    ("Clojure", "Clojure"),
    ("Haskell", "Haskell"),
]

_LANGUAGE_ALIASES: list[tuple[str, str]] = DEFAULT_LANGUAGE_ALIASES.copy()
_TOOL_ALIASES: list[tuple[str, str]] = []
_JOB_TYPE_ALIASES: list[tuple[str, str]] = []
_CONDITION_ALIASES: list[tuple[str, str]] = []

# Common job-title patterns
TITLE_PATTERNS = [
    r"(?:Job\s+Title|Position|Role)[:\s]+([^\n|]+)",
]

US_STATE_CODES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|"
    "MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"
)

# Labeled-field patterns require a colon and a line start, not just trailing
# whitespace: "Location"/"Company" show up constantly in ordinary page chrome
# and boilerplate, so matching on whitespace alone grabs the middle of an
# unrelated sentence. Anchoring to "^Label:" is what a real field line
# actually looks like.
COMPANY_PATTERNS = [
    r"(?im:^\s*(?:Company|Employer|Organization)\s*:\s*([^\n|,]{2,80}))",
    r"\bat\s+([A-Z][\w&.,'\-]*(?:\s+[A-Z][\w&.,'\-]*){0,4})\s*(?:\n|-|–|\|)",
]
LOCATION_PATTERNS = [
    r"(?im:^\s*Location\s*:\s*([^\n|]{2,80}))",
    rf"\b([A-Z][a-zA-Z. ]+,\s*(?:{US_STATE_CODES})\b(?:\s*\d{{5}})?)",
    r"\b(Remote(?:\s*[-,]\s*[A-Za-z ]+)?)\b",
]


def _first_match(text: str, patterns: list[str]) -> str:
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1 if m.groups() else 0).strip()
    return ""


def extract_job_title(text: str) -> str:
    """Try to pull a job title from the beginning of the description."""
    for pat in TITLE_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    # Fall back to first non-empty line
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return ""


def extract_company(text: str) -> str:
    """Try to pull a company name from a labeled field or 'at <Company>' phrasing."""
    return _first_match(text, COMPANY_PATTERNS)


def extract_location(text: str) -> str:
    """Try to pull a location from a labeled field, a 'City, ST' pattern, or 'Remote'."""
    return _first_match(text, LOCATION_PATTERNS)


def configure_extraction_aliases(
    language_aliases: list[tuple[str, str]] | None,
    tool_aliases: list[tuple[str, str]] | None,
    job_type_aliases: list[tuple[str, str]] | None = None,
    condition_aliases: list[tuple[str, str]] | None = None,
) -> None:
    """Configure discovery/reporting aliases loaded from settings files."""
    global _LANGUAGE_ALIASES
    global _TOOL_ALIASES
    global _JOB_TYPE_ALIASES
    global _CONDITION_ALIASES

    _LANGUAGE_ALIASES = language_aliases.copy() if language_aliases else DEFAULT_LANGUAGE_ALIASES.copy()
    _TOOL_ALIASES = tool_aliases.copy() if tool_aliases else []
    _JOB_TYPE_ALIASES = job_type_aliases.copy() if job_type_aliases else []
    _CONDITION_ALIASES = condition_aliases.copy() if condition_aliases else []


def _term_regex(term: str) -> str:
    """Build a safe regex for matching technology terms in free-form text."""
    escaped = re.escape(term)
    if re.fullmatch(r"[A-Za-z0-9_]+", term):
        return rf"\b{escaped}\b"
    return rf"(?<!\w){escaped}(?!\w)"


def _extract_alias_values(text: str, aliases: list[tuple[str, str]]) -> str:
    """Return unique reporting values whose discovery term appears in text."""
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
    """Return a comma-separated list of configured programming languages."""
    return _extract_alias_values(text, _LANGUAGE_ALIASES)


def extract_tools(text: str) -> str:
    """Return a comma-separated list of configured tools."""
    return _extract_alias_values(text, _TOOL_ALIASES)


def extract_job_type(text: str) -> str:
    """Return a comma-separated list of configured job types (see settings/jobtypes.txt)."""
    return _extract_alias_values(text, _JOB_TYPE_ALIASES)


def extract_conditions(text: str) -> str:
    """Return a comma-separated list of configured conditions (see settings/conditions.txt)."""
    return _extract_alias_values(text, _CONDITION_ALIASES)


def extract_salary(text: str) -> str:
    """
    Try to extract a salary range from free-form job description text.
    Handles patterns like:
      $100,000 - $200,000 / year
      100K–200K
      Up to $300K
      $150,000+
      Salary: $120k to $180k
    """
    patterns = [
        # $X - $Y  or  $X–$Y  (with optional K/k)
        r"\$[\d,]+(?:\.\d+)?[kK]?\s*(?:to|-|–|—)\s*\$[\d,]+(?:\.\d+)?[kK]?",
        # XK - YK  (no dollar sign)
        r"\b\d{2,3}[kK]\s*(?:to|-|–|—)\s*\d{2,3}[kK]\b",
        # $X,000 to $Y,000
        r"\$[\d,]{6,}\s*(?:to|-|–|—)\s*\$[\d,]{6,}",
        # Up to $X
        r"[Uu]p\s+to\s+\$[\d,]+(?:\.\d+)?[kK]?",
        # $X+  or  $Xk+
        r"\$[\d,]+(?:\.\d+)?[kK]?\+",
        # Salary: $X
        r"[Ss]alary[:\s]+\$[\d,]+(?:\.\d+)?[kK]?(?:\s*(?:to|-|–)\s*\$[\d,]+(?:\.\d+)?[kK]?)?",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(0).strip()
    return ""


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
        elif "condition" in attr_lower:
            result[attr] = extract_conditions(text)
        elif "type" in attr_lower:
            result[attr] = extract_job_type(text)
        elif "salary" in attr_lower or "range" in attr_lower:
            result[attr] = extract_salary(text)
        else:
            result[attr] = ""
    return result


# ---------------------------------------------------------------------------
# Selenium helpers
# ---------------------------------------------------------------------------
#
# Several sites (TopResume, LinkedIn, ...) require the user to be signed in.
# A browser instance launched and owned by this app has no way to present a
# sign-in form to the user, so instead we attach to a Chrome instance the
# user starts themselves ahead of time, with a persistent profile that keeps
# them signed in across runs:
#
#   "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
#       --remote-debugging-port=9222 ^
#       --user-data-dir="C:\Users\%USERNAME%\ChromeAutomationProfile"

DEBUG_BROWSER_ADDRESS = "127.0.0.1:9222"
DEBUG_BROWSER_LAUNCH_COMMAND = (
    r'"C:\Program Files\Google\Chrome\Application\chrome.exe" '
    r'--remote-debugging-port=9222 '
    r'--user-data-dir="C:\Users\%USERNAME%\ChromeAutomationProfile"'
)


def is_debug_browser_running(debugger_address: str = DEBUG_BROWSER_ADDRESS) -> bool:
    """Return True when a Chrome instance is listening at `debugger_address`."""
    try:
        resp = requests.get(f"http://{debugger_address}/json/version", timeout=3)
        return resp.ok
    except requests.RequestException:
        return False


def _ensure_open_page(debugger_address: str) -> None:
    """Chromedriver needs at least one open tab to attach to; open one if none exist."""
    try:
        resp = requests.get(f"http://{debugger_address}/json", timeout=3)
        resp.raise_for_status()
        pages = resp.json()
    except requests.RequestException:
        return

    if pages:
        return

    for method in (requests.put, requests.get):
        try:
            method(f"http://{debugger_address}/json/new", timeout=3).raise_for_status()
            return
        except requests.RequestException:
            continue


def build_driver(debugger_address: str = DEBUG_BROWSER_ADDRESS) -> webdriver.Chrome:
    """Attach to the user-launched debug Chrome instance (see module notes above)."""
    _ensure_open_page(debugger_address)

    options = Options()
    options.debugger_address = debugger_address

    service = Service(ChromeDriverManager().install())
    try:
        driver = webdriver.Chrome(service=service, options=options)
    except WebDriverException as exc:
        raise RuntimeError(
            f"Unable to attach to the debug Chrome browser at {debugger_address}: {exc}\n"
            f"Make sure it is running with:\n  {DEBUG_BROWSER_LAUNCH_COMMAND}\nand try again."
        ) from exc

    return driver


# ---------------------------------------------------------------------------
# Base extractor
# ---------------------------------------------------------------------------

class BaseExtractor(ABC):
    """All site-specific extractors inherit from this."""

    def extract(self, url: str, attributes: list[str]) -> list[dict[str, Any]]:
        """
        Open `url`, enumerate all job listings, and return a list of dicts:
            {
                "job_url": str,
                "attributes": {attr_name: value, ...},
            }
        """
        driver = build_driver()
        try:
            return self._extract(driver, url, attributes)
        finally:
            # driver.quit() only ends this attached session/local chromedriver
            # helper process — it does not close the user's debug browser.
            driver.quit()

    @abstractmethod
    def _extract(
        self,
        driver: webdriver.Chrome,
        url: str,
        attributes: list[str],
    ) -> list[dict[str, Any]]:
        """Site-specific implementation."""
        ...

    # Convenience helpers for subclasses
    @staticmethod
    def wait(driver: webdriver.Chrome, timeout: int = 15) -> WebDriverWait:
        return WebDriverWait(driver, timeout)

    @staticmethod
    def sleep(seconds: float) -> None:
        time.sleep(seconds)
