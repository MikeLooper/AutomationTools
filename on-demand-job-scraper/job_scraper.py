"""
job_scraper.py — On-demand job scraper.

Reads the URL currently open in the user's system browser, scrapes it with a
predefined extractor when the site is recognized (falling back to a generic
heuristic extractor otherwise).

For a LinkedIn search-results page with a card list, this clicks through
every card (via the live-browser-attach session — see README) and writes an
HTML/JSON report of all of them, matching job-search-python's report layout.
Anything else prints a single-job summary to the console.

Usage:
    python job_scraper.py
    python job_scraper.py --url https://example.com/jobs/12345
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from browser_reader import BrowserNotFoundError, get_active_browser_url
from extractors import linkedin as linkedin_module
from extractors.base import configure_extraction_aliases
from extractors.dispatcher import get_extractor
from list_scraper import scrape_all_cards
from matcher import apply_exclusions, compute_match, parse_exclusion_rules
from page_fetcher import fetch, find_debug_port, open_in_browser
from reporter import generate_report

BASE_DIR = Path(__file__).resolve().parent
SETTINGS_DIR = BASE_DIR / "settings"
REPORT_BASE = BASE_DIR / "reports"
DEFAULT_ATTRIBUTES_PATH = SETTINGS_DIR / "attributes.txt"
DEFAULT_PROGRAMMING_LANGUAGES_PATH = SETTINGS_DIR / "programminglanguages.txt"
DEFAULT_TOOLS_PATH = SETTINGS_DIR / "tools.txt"
DEFAULT_TARGETS_PATH = SETTINGS_DIR / "targets.txt"
DEFAULT_EXCLUSIONS_PATH = SETTINGS_DIR / "exclusions.txt"
DEFAULT_MATCH_PCT = 75


def load_lines(path: str) -> list[str]:
    result = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                result.append(stripped)
    return result


def load_alias_lines(path: str) -> list[tuple[str, str]]:
    aliases: list[tuple[str, str]] = []
    for line in load_lines(path):
        if ":" in line:
            discovery, reporting = line.split(":", 1)
            aliases.append((discovery.strip(), reporting.strip()))
        else:
            aliases.append((line, line))
    return aliases


def print_summary(result: dict, window_title: str, fetch_method: str, fetch_warning: str | None) -> None:
    print("\n" + "=" * 60)
    print("JOB SUMMARY")
    print("=" * 60)
    for name, value in result["attributes"].items():
        print(f"{name:<22}: {value or '(not found)'}")
    print("-" * 60)
    print(f"{'Source':<22}: {result['source']}")
    print(f"{'URL':<22}: {result['job_url']}")
    print(f"{'Browser tab':<22}: {window_title}")
    print(f"{'Fetch method':<22}: {'live browser session (authenticated)' if fetch_method == 'live-browser' else 'plain HTTP request'}")
    if result.get("note"):
        print(f"\nNote: {result['note']}")
    if fetch_warning:
        print(f"\nWarning: {fetch_warning}")
    print("=" * 60)


def write_list_report(url: str, jobs: list[dict], match_pct: int, targets_path: str, exclusions_path: str) -> Path:
    """Score every scraped job and write an HTML+JSON report, job-search-python style."""
    targets = load_lines(targets_path)
    exclusion_rules, exclusion_warnings = parse_exclusion_rules(load_lines(exclusions_path))

    scored_jobs = []
    for job in jobs:
        score, details = compute_match(job["attributes"], targets)
        preliminary_recommended = score >= match_pct
        if preliminary_recommended:
            excluded, exclusion_details = apply_exclusions(job["attributes"], exclusion_rules)
        else:
            excluded, exclusion_details = False, []
        job["match_score"] = score
        job["match_details"] = details
        job["excluded"] = excluded
        job["exclusion_details"] = exclusion_details
        job["recommended"] = preliminary_recommended and not excluded
        scored_jobs.append(job)
        flag = "RECOMMENDED" if job["recommended"] else ("EXCLUDED" if excluded else "")
        print(f"  [{score:3d}%] {job['attributes'].get('Job Title', '(no title)')}  {flag}")

    results = [{"url": url, "jobs": scored_jobs}]

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    report_dir = REPORT_BASE / timestamp
    report_dir.mkdir(parents=True, exist_ok=True)

    json_path = report_dir / "report.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump({
            "generated": timestamp,
            "match_pct": match_pct,
            "exclusion_warnings": exclusion_warnings,
            "results": results,
        }, fh, indent=2)

    html_path = generate_report(
        results, match_pct, timestamp, report_dir,
        exclusion_warnings=exclusion_warnings,
    )
    return html_path


def main() -> None:
    parser = argparse.ArgumentParser(description="On-demand job scraper")
    parser.add_argument("--url", default="", help="Job posting URL to use instead of reading the browser's active tab")
    parser.add_argument("--attributes", default=str(DEFAULT_ATTRIBUTES_PATH))
    parser.add_argument("--programminglanguages", default=str(DEFAULT_PROGRAMMING_LANGUAGES_PATH))
    parser.add_argument("--tools", default=str(DEFAULT_TOOLS_PATH))
    parser.add_argument("--targets", default=str(DEFAULT_TARGETS_PATH))
    parser.add_argument("--exclusions", default=str(DEFAULT_EXCLUSIONS_PATH))
    parser.add_argument("--match-pct", type=int, default=DEFAULT_MATCH_PCT)
    parser.add_argument(
        "--debug-port", type=int, default=None,
        help="Remote-debugging port of a dedicated, already-logged-in browser profile (see README). Tried in addition to the default 9222.",
    )
    args = parser.parse_args()

    attributes = load_lines(args.attributes)
    configure_extraction_aliases(
        load_alias_lines(args.programminglanguages),
        load_alias_lines(args.tools),
    )

    window_title = ""
    if args.url.strip():
        url = args.url.strip()
    else:
        try:
            url, window_title = get_active_browser_url()
        except BrowserNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"Reading currently open page: {url}")

    module, is_known_site = get_extractor(url)
    if not is_known_site:
        print(f"  Site not pre-programmed for {url} - using generic extraction.")

    # A card-list page (currently: LinkedIn search results) needs real clicks
    # to see each job, which only the live-browser-attach session can do.
    # Gated on the target URL actually being a LinkedIn one — otherwise
    # scrape_all_cards would happily click through whatever LinkedIn tab is
    # open in the attached browser even when a different site/URL was asked
    # for, since it only checks the live browser's own tabs, not `url`.
    jobs = None
    if module is linkedin_module:
        port = find_debug_port(extra_ports=[args.debug_port] if args.debug_port else None)
        if port is not None:
            jobs = scrape_all_cards(port, module, attributes)

    if jobs:
        html_path = write_list_report(url, jobs, args.match_pct, args.targets, args.exclusions)
        if not open_in_browser(port, html_path):
            os.startfile(str(html_path))
        print(f"\nReport written to: {html_path.parent}")
        print(f"  HTML: {html_path.name}")
        print(f"  JSON: {(html_path.parent / 'report.json').name}")
        return

    try:
        fetch_result = fetch(url, debug_port=args.debug_port)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    result = module.parse(url, fetch_result.html, attributes)
    print_summary(result, window_title, fetch_result.method, fetch_result.warning)


if __name__ == "__main__":
    main()
