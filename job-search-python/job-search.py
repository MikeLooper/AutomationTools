"""
job-search — Main entry point for the Job Search Agent.

Usage:
    python job-search
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from extractors.dispatcher import get_extractor
from extractors.base import configure_extraction_aliases
from matcher import apply_exclusions, compute_match, parse_exclusion_rules
from reporter import generate_report

BASE_DIR = Path(__file__).resolve().parent
SETTINGS_DIR = BASE_DIR / "settings"
REPORT_BASE = Path(r"C:\Working\Storage\Dev\GitHub\AIAssistants\job-search-python\reports")
DEFAULT_URLS_PATH = SETTINGS_DIR / "urls.txt"
DEFAULT_ATTRIBUTES_PATH = SETTINGS_DIR / "attributes.txt"
DEFAULT_TARGETS_PATH = SETTINGS_DIR / "targets.txt"
DEFAULT_EXCLUSIONS_PATH = SETTINGS_DIR / "exclusions.txt"
DEFAULT_PROGRAMMING_LANGUAGES_PATH = SETTINGS_DIR / "programminglanguages.txt"
DEFAULT_TOOLS_PATH = SETTINGS_DIR / "tools.txt"
DEFAULT_MATCH_PCT = 75
DEFAULT_MAX_JOBS_PER_URL = 0


def load_lines(path: str) -> list[str]:
    """Return non-blank, non-comment lines from a text file."""
    result = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                result.append(stripped)
    return result


def load_alias_lines(path: str) -> list[tuple[str, str]]:
    """Return discovery/reporting aliases from non-blank, non-comment lines."""
    aliases: list[tuple[str, str]] = []
    for line in load_lines(path):
        if ":" in line:
            discovery, reporting = line.split(":", 1)
            discovery = discovery.strip()
            reporting = reporting.strip()
            if discovery and reporting:
                aliases.append((discovery, reporting))
            elif discovery:
                aliases.append((discovery, discovery))
            elif reporting:
                aliases.append((reporting, reporting))
        else:
            aliases.append((line, line))
    return aliases


def main() -> None:
    parser = argparse.ArgumentParser(description="Job Search Agent")
    parser.add_argument(
        "--urls",
        default=str(DEFAULT_URLS_PATH),
        help=f"Path to search-URL list file (default: {DEFAULT_URLS_PATH})",
    )
    parser.add_argument(
        "--attributes",
        default=str(DEFAULT_ATTRIBUTES_PATH),
        help=f"Path to attributes list file (default: {DEFAULT_ATTRIBUTES_PATH})",
    )
    parser.add_argument(
        "--targets",
        default=str(DEFAULT_TARGETS_PATH),
        help=f"Path to target rules file (default: {DEFAULT_TARGETS_PATH})",
    )
    parser.add_argument(
        "--exclusions",
        default=str(DEFAULT_EXCLUSIONS_PATH),
        help=f"Path to exclusions rules file (default: {DEFAULT_EXCLUSIONS_PATH})",
    )
    parser.add_argument(
        "--programminglanguages",
        default=str(DEFAULT_PROGRAMMING_LANGUAGES_PATH),
        help=(
            "Path to programming languages alias file "
            f"(default: {DEFAULT_PROGRAMMING_LANGUAGES_PATH})"
        ),
    )
    parser.add_argument(
        "--tools",
        default=str(DEFAULT_TOOLS_PATH),
        help=f"Path to tools alias file (default: {DEFAULT_TOOLS_PATH})",
    )
    parser.add_argument(
        "--match-pct",
        default=DEFAULT_MATCH_PCT,
        type=int,
        help=(
            "Minimum match percentage to flag a job as recommended (0-100) "
            f"(default: {DEFAULT_MATCH_PCT})"
        ),
    )
    parser.add_argument(
        "--max-jobs-per-url",
        default=DEFAULT_MAX_JOBS_PER_URL,
        type=int,
        help=(
            "Maximum number of jobs to process per URL (0 means no limit) "
            f"(default: {DEFAULT_MAX_JOBS_PER_URL})"
        ),
    )
    args = parser.parse_args()

    urls       = load_lines(args.urls)
    attributes = load_lines(args.attributes)
    targets    = load_lines(args.targets)
    exclusion_lines = load_lines(args.exclusions)
    language_aliases = load_alias_lines(args.programminglanguages)
    tool_aliases = load_alias_lines(args.tools)
    match_pct  = args.match_pct
    max_jobs_per_url = args.max_jobs_per_url
    exclusion_rules, exclusion_warnings = parse_exclusion_rules(exclusion_lines)

    if max_jobs_per_url < 0:
        print("ERROR: --max-jobs-per-url must be 0 or greater", file=sys.stderr)
        sys.exit(1)

    configure_extraction_aliases(language_aliases, tool_aliases)

    if not urls:
        print("ERROR: No URLs found in", args.urls, file=sys.stderr)
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    report_dir = REPORT_BASE / timestamp
    report_dir.mkdir(parents=True, exist_ok=True)

    all_results: list[dict] = []

    for url in urls:
        print(f"\n{'='*60}")
        print(f"Processing: {url}")
        print('='*60)

        extractor = get_extractor(url)
        try:
            jobs = extractor.extract(url, attributes)
            if max_jobs_per_url > 0:
                jobs = jobs[:max_jobs_per_url]
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR extracting jobs from {url}: {exc}", file=sys.stderr)
            all_results.append({"url": url, "jobs": [], "error": str(exc)})
            continue

        scored_jobs = []
        for job in jobs:
            score, details = compute_match(job["attributes"], targets)
            preliminary_recommended = score >= match_pct
            if preliminary_recommended:
                excluded, exclusion_details = apply_exclusions(job["attributes"], exclusion_rules)
            else:
                excluded, exclusion_details = False, []
            job["match_score"]   = score
            job["match_details"] = details
            job["excluded"]      = excluded
            job["exclusion_details"] = exclusion_details
            job["recommended"]   = preliminary_recommended and (not excluded)
            scored_jobs.append(job)
            if job["recommended"]:
                flag = "✅ RECOMMENDED"
            elif excluded:
                flag = "🚫 EXCLUDED"
            else:
                flag = ""
            print(f"  [{score:3d}%] {job['attributes'].get('Job Title','(no title)')}"
                  f"  {flag}")

        all_results.append({"url": url, "jobs": scored_jobs})

    # Write JSON
    json_path = report_dir / "report.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump({
            "generated": timestamp,
            "match_pct": match_pct,
            "max_jobs_per_url": max_jobs_per_url,
            "exclusion_warnings": exclusion_warnings,
            "results": all_results,
        }, fh, indent=2)

    # Write HTML
    html_path = generate_report(
        all_results,
        match_pct,
        timestamp,
        report_dir,
        exclusion_warnings=exclusion_warnings,
    )
    os.startfile(str(html_path))

    print(f"\n{'='*60}")
    print(f"Report written to: {report_dir}")
    print(f"  HTML: {html_path.name}")
    print(f"  JSON: {json_path.name}")


if __name__ == "__main__":
    main()
