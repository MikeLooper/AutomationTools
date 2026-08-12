"""
extractors/base.py — Base extractor class and shared attribute-extraction helpers.
"""

import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

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

# Common job-title patterns
TITLE_PATTERNS = [
    r"(?:Job\s+Title|Position|Role)[:\s]+([^\n|]+)",
]


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


def configure_extraction_aliases(
    language_aliases: list[tuple[str, str]] | None,
    tool_aliases: list[tuple[str, str]] | None,
) -> None:
    """Configure discovery/reporting aliases loaded from settings files."""
    global _LANGUAGE_ALIASES
    global _TOOL_ALIASES

    _LANGUAGE_ALIASES = language_aliases.copy() if language_aliases else DEFAULT_LANGUAGE_ALIASES.copy()
    _TOOL_ALIASES = tool_aliases.copy() if tool_aliases else []


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
        elif "language" in attr_lower or "programming" in attr_lower:
            result[attr] = extract_programming_languages(text)
        elif "tool" in attr_lower:
            result[attr] = extract_tools(text)
        elif "salary" in attr_lower or "range" in attr_lower:
            result[attr] = extract_salary(text)
        else:
            result[attr] = ""
    return result


# ---------------------------------------------------------------------------
# Selenium helpers
# ---------------------------------------------------------------------------

def build_driver(headless: bool = True) -> webdriver.Chrome:
    """Create and return a Chrome WebDriver instance."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--remote-debugging-port=0")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    chrome_binary_candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Chromium\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Chromium\Application\chrome.exe"),
        Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in chrome_binary_candidates:
        if candidate.exists():
            options.binary_location = str(candidate)
            break

    service = Service(ChromeDriverManager().install())
    try:
        driver = webdriver.Chrome(service=service, options=options)
    except WebDriverException as exc:
        raise RuntimeError(
            "Unable to start Chrome for Selenium. Ensure Google Chrome or Chromium is "
            "installed and matches the ChromeDriver version."
        ) from exc

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


# ---------------------------------------------------------------------------
# Base extractor
# ---------------------------------------------------------------------------

class BaseExtractor(ABC):
    """All site-specific extractors inherit from this."""

    # Override in subclass to run headful (visible) browser, e.g. for login walls
    HEADLESS: bool = True

    def extract(self, url: str, attributes: list[str]) -> list[dict[str, Any]]:
        """
        Open `url`, enumerate all job listings, and return a list of dicts:
            {
                "job_url": str,
                "attributes": {attr_name: value, ...},
            }
        """
        driver = build_driver(headless=self.HEADLESS)
        try:
            return self._extract(driver, url, attributes)
        finally:
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
