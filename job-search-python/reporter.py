"""
reporter.py — Generates the HTML report using a Jinja2 template.
"""

from pathlib import Path
from jinja2 import Environment, FileSystemLoader


TEMPLATE_DIR = Path(__file__).parent / "templates"


def generate_report(
    results: list[dict],
    match_pct: int,
    timestamp: str,
    report_dir: Path,
    exclusion_warnings: list[str] | None = None,
) -> Path:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("report.html.j2")

    total_jobs = sum(len(r.get("jobs", [])) for r in results)
    recommended = sum(
        1 for r in results for j in r.get("jobs", []) if j.get("recommended")
    )
    recommended_jobs: list[dict] = []
    for result in results:
        source_url = result.get("url", "")
        for job in result.get("jobs", []):
            if not job.get("recommended"):
                continue
            attrs = job.get("attributes", {})
            recommended_jobs.append(
                {
                    "job_title": attrs.get("Job Title", "(no title)"),
                    "job_url": job.get("job_url", ""),
                    "match_score": job.get("match_score", 0),
                    "source_url": source_url,
                }
            )

    html = template.render(
        timestamp=timestamp,
        match_pct=match_pct,
        results=results,
        total_jobs=total_jobs,
        recommended=recommended,
        recommended_jobs=recommended_jobs,
        exclusion_warnings=exclusion_warnings or [],
    )

    out_path = report_dir / "report.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path
