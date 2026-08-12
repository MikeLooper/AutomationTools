# Job Search Agent

An automated job search agent that visits multiple job sites, extracts job descriptions, and matches them against target attributes.

## Requirements

- Python 3.10+
- Google Chrome or Chromium (for Selenium)
- ChromeDriver matching your Chrome version (auto-managed via `webdriver-manager`)

## Installation

```bash
C:\Working\Storage\Dev\GitHub\AIAssistants\job-search-python
pip install -r requirements.txt
```

## Usage

```bash
python job-search
```

The script defaults to:

- `settings/urls.txt`
- `settings/attributes.txt`
- `settings/targets.txt`
- `settings/exclusions.txt`
- `settings/programminglanguages.txt`
- `settings/tools.txt`
- `--match-pct 75`
- `--max-jobs-per-url 0` (no limit)

All values can still be overridden:

```bash
python job-search \
  --urls settings/urls.txt \
  --attributes settings/attributes.txt \
  --targets settings/targets.txt \
  --exclusions settings/exclusions.txt \
  --programminglanguages settings/programminglanguages.txt \
  --tools settings/tools.txt \
  --match-pct 75 \
  --max-jobs-per-url 25
```

### Arguments

| Argument | Description |
|----------|-------------|
| `--urls` | Path to a file containing one search URL per line. Defaults to `settings/urls.txt` |
| `--attributes` | Path to a file listing the attributes to extract (e.g. `Job Title`, `Programming Language`, `Tools`, `Salary Range`). Defaults to `settings/attributes.txt` |
| `--targets` | Path to a file listing target attribute values (e.g. `Job Title=Solutions Architect`). Defaults to `settings/targets.txt` |
| `--exclusions` | Path to a file listing exclusion rules. Defaults to `settings/exclusions.txt` |
| `--programminglanguages` | Path to programming-language aliases used for discovery/reporting. Defaults to `settings/programminglanguages.txt` |
| `--tools` | Path to tool aliases used for discovery/reporting. Defaults to `settings/tools.txt` |
| `--match-pct` | Integer 0–100. Jobs scoring ≥ this value are flagged as **recommended**. Defaults to `75` |
| `--max-jobs-per-url` | Integer ≥ 0. Limits how many extracted jobs are processed for each URL. `0` means no limit. Defaults to `0` |

## Input File Formats

### settings/urls.txt
One URL per line. Blank lines and lines starting with `#` are ignored.

```
https://www.dice.com/jobs?q=Solutions+Architect&...
https://www.linkedin.com/jobs/search/?keywords=solutions+architect&...
```

### settings/attributes.txt
One attribute name per line.

```
Job Title
Programming Language
Tools
Salary Range
```

### settings/targets.txt
One target rule per line. Supported operators:

| Syntax | Meaning |
|--------|---------|
| `Job Title=Solutions Architect` | Exact (case-insensitive) match |
| `Job Title=Solutions Architect OR Software Engineer` | Match if any listed value matches |
| `Salary Range Includes 200K` | The discovered salary range must span $200,000 (i.e. min ≤ 200K ≤ max) |
| `Programming Language=Python` | Exact match |

```
Job Title=Solutions Architect
Programming Language=Python OR Java OR C#
Salary Range Includes 200K
```

### settings/exclusions.txt
One exclusion rule per line. Any matching exclusion marks the job as excluded and not recommended.

Rules must include `=`:

- Left side: attribute name to compare (case-insensitive exact name match)
- Right side: value to compare against extracted attribute value (case-insensitive equals or contains)
- Right side may include ` OR ` for logical OR matching

Lines missing `=` are ignored and listed as notes in the HTML report.

```
Job Title=Intern OR Junior
Programming Language=COBOL
Tools=Not specified
```

### settings/programminglanguages.txt
One alias per line. These values are the source of truth for `Programming Language` extraction.

- No colon: the same value is used for discovery and reporting.
- With colon: `discovery:reporting`.

```
JavaScript
Node.js
CSharp:C#
ReactJS:React
```

### settings/tools.txt
One alias per line. These values are the source of truth for `Tools` extraction.

- No colon: the same value is used for discovery and reporting.
- With colon: `discovery:reporting`.
- Only the first colon is treated as the separator.

```
Amazon Web Services:AWS
Google Cloud Platform:GCP
Model Context Protocol:MCP
PostgreSQL
```

## Output

Reports are written to:

```
C:\Working\Storage\Dev\GitHub\AIAssistants\job-search\reports\YYYY-MM-DD_HH-MM\
```

Each run produces:
- `report.html` — human-readable HTML report
- `report.json` — machine-readable JSON of all results

`report.json` also includes:
- `exclusion_warnings` — ignored exclusion lines and reasons
- Per-job `excluded` and `exclusion_details`

After the files are written, the script opens `report.html` in your browser.

### Exclusion Behavior

- A job can match target rules and still be excluded by `settings/exclusions.txt`.
- Excluded jobs are flagged as excluded and never recommended for follow-up.
- Exclusions are evaluated by attribute name and value with case-insensitive equals/contains matching.

## Supported Job Sites

| Site | Extraction Method |
|------|-------------------|
| Connecting Colorado | Selenium - clicks each job card in the left panel and reads details from the right pane |
| Dice | Selenium — clicks each job card in the left panel |
| Glassdoor | Selenium — clicks each job card, handles sign-in wall |
| Greenhouse | Selenium — standard job board |
| LinkedIn | Selenium — clicks each job card (login may be required for full details) |
| Remotive | requests + BeautifulSoup (static HTML) |

## Alternative AI Tools

For richer LLM-based attribute extraction, consider:

| Tool / Model | How to use |
|---|---|
| **OpenAI GPT-4o** | Replace the regex extractors in `extractors/base.py` with a call to the OpenAI Chat Completions API. Send the raw job description text and ask it to return JSON with the required attributes. |
| **Anthropic Claude 3.5 Sonnet** | Same pattern — pipe job text into a Claude prompt asking for structured extraction. Excellent at reasoning about salary ranges stated in non-standard prose. |
| **LangChain + any LLM** | Use LangChain's `WebBaseLoader` + an extraction chain to scrape and parse in one pipeline. Simplifies site-specific handling. |
| **Playwright + AI SDK** | Microsoft's Playwright MCP server can be driven by an LLM agent to handle complex JS-heavy pages better than Selenium. |
| **Bright Data / ScrapingBee** | Proxy-based scraping APIs that handle bot-detection on LinkedIn / Glassdoor, reducing need for manual Selenium cookie handling. |
