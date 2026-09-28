# Job Search Agent

An automated job search agent that visits multiple job sites, extracts job descriptions, and matches them against target attributes.

## Requirements

- Python 3.10+
- Google Chrome (for Selenium)
- ChromeDriver matching your Chrome version (auto-managed via `webdriver-manager`)

## Installation

```bash
C:\Working\Storage\Dev\GitHub\AIAssistants\job-search-python
pip install -r requirements.txt
```

## Usage

Some sites (TopResume, LinkedIn, ...) require you to be signed in. Since the app doesn't launch
its own browser, it instead attaches to a Chrome instance that you start yourself, with a
persistent profile that keeps you signed in across runs. **Before running the app**, start Chrome
with remote debugging enabled:

```bash
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\Users\%USERNAME%\ChromeAutomationProfile"
```

Sign in to any sites that require it in that browser window, then leave it open and run:

```bash
python job-search
```

If this debug browser isn't running and reachable at `127.0.0.1:9222`, the app stops immediately
and tells you to start it before restarting the application.

At startup, the app prints one log line with the effective runtime parameters, including
which URL source is being used (`--url` or `--urls`) and all active file/threshold settings.

The script defaults to:

- `settings/urls.txt`
- `settings/attributes.txt`
- `settings/targets.txt`
- `settings/exclusions.txt`
- `settings/programminglanguages.txt`
- `settings/tools.txt`
- `settings/jobtypes.txt`
- `settings/conditions.txt`
- `--url` not set (uses `--urls` file)
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
  --jobtypes settings/jobtypes.txt \
  --conditions settings/conditions.txt \
  --match-pct 75 \
  --max-jobs-per-url 25
```

Process only one URL (and ignore `--urls` file input):

```bash
python job-search --url "https://remotive.com/remote-jobs/software-dev"
```

### Arguments

| Argument | Description |
|----------|-------------|
| `--urls` | Path to a file containing one search URL per line. Defaults to `settings/urls.txt` |
| `--url` | Single search URL to process. When provided, this overrides `--urls` and only this URL is used.  Enclose this URL in double quotes to prevent mis-reading of arguments, |
| `--attributes` | Path to a file listing the attributes to extract (e.g. `Job Title`, `Job Type`, `Company`, `Location`, `Programming Language`, `Tools`, `Condition`, `Salary Range`). Defaults to `settings/attributes.txt` |
| `--targets` | Path to a file listing target attribute values (e.g. `Job Title=Solutions Architect`). Defaults to `settings/targets.txt` |
| `--exclusions` | Path to a file listing exclusion rules. Defaults to `settings/exclusions.txt` |
| `--programminglanguages` | Path to programming-language aliases used for discovery/reporting. Defaults to `settings/programminglanguages.txt` |
| `--tools` | Path to tool aliases used for discovery/reporting. Defaults to `settings/tools.txt` |
| `--jobtypes` | Path to job type aliases used for discovery/reporting. Defaults to `settings/jobtypes.txt` |
| `--conditions` | Path to condition aliases used for discovery/reporting. Defaults to `settings/conditions.txt` |
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
Job Type
Company
Location
Programming Language
Tools
Condition
Salary Range
```

### settings/targets.txt
One target rule per line. Supported operators:

| Syntax | Meaning |
|--------|---------|
| `Job Title=Solutions Architect` | Exact (case-insensitive) match |
| `Job Title=Solutions Architect OR Software Engineer` | Match if any listed value matches |
| `Salary Range Includes 200K` | The discovered salary range must span $200,000 (i.e. min ≤ 200K ≤ max) |
| `Salary Range Is Greater Than 200K` | Any bound of the discovered salary range must exceed $200,000 |
| `Salary Range Is Less Than 100K` | Any bound of the discovered salary range must be below $100,000 |
| `Salary Range Equals 200K` | One of the discovered salary range's stated figures must equal $200,000 exactly |
| `Programming Language=Python` | Exact match |

Any of the four Salary Range comparisons can be OR'd together on one line, e.g.
`Salary Range Includes 200K OR Is Greater Than 250K`.

```
Job Title=Solutions Architect
Programming Language=Python OR Java OR C#
Salary Range Includes 200K OR Is Greater Than 250K
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
Condition=Security Clearance
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

### settings/jobtypes.txt
One alias per line. These values are the source of truth for `Job Type` extraction.

- No colon: the same value is used for discovery and reporting.
- With colon: `discovery:reporting`.

```
Contract
Full Time
Full-time
Hybrid
On-site
Permanent
Remote
Temporary
```

### settings/conditions.txt
One alias per line. These values are the source of truth for `Condition` extraction.

- No colon: the same value is used for discovery and reporting (exact match, case-insensitive).
- With colon: `discovery:reporting` — the left side is matched (exact, case-insensitive) and the right side is substituted for reporting.
- Only the first colon is treated as the separator.

```
ability to obtain a Secret clearance:Security Clearance
clearance is required:Security Clearance
Clearance Level:Security Clearance
Minimum Clearance Required:Security Clearance
Security Clearance
Secret clearance:Security Clearance
Top Secret clearance:Security Clearance
```

Conditions found in a job description are reported in the `Condition` attribute and can be used in
`settings/exclusions.txt` like any other attribute, e.g. `Condition=Security Clearance` excludes any
job whose extracted `Condition` value contains "Security Clearance".

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
- `parameters` — all CLI parameters with description, value, and whether each was explicitly supplied
- `effective_parameters` — resolved runtime settings actually used by the run

After the files are written, the script opens `report.html` in your browser.

`report.html` includes:
- Top summary bar (URLs, jobs, recommended)
- Recommended follow-up section
- URL-by-URL job details
- Run Parameters section (at the bottom)
- Run Summary section (at the bottom) with:
  - Number of URLs checked
  - Number of jobs checked
  - Match-score distribution (count of jobs for each score found)

### Exclusion Behavior

- Every job description is compared against `settings/exclusions.txt`, regardless of its match score.
- A job can match target rules and still be excluded.
- Excluded jobs are flagged as excluded (with the matching rule shown) and never recommended for follow-up.
- Exclusions are evaluated by attribute name and value with case-insensitive equals/contains matching.

## Supported Job Sites

| Site | Extraction Method |
|------|-------------------|
| Connecting Colorado | Selenium - clicks each job card in the left panel and reads details from the right pane |
| Dice | Selenium — clicks each job card in the left panel |
| Greenhouse | Selenium — standard job board |
| LinkedIn | Selenium — clicks each job card (login may be required for full details) |
| Remotive | requests + BeautifulSoup (static HTML) |
| TopResume (Careerio) | Selenium — activates the `Search` tab, clicks each job card (using the card's own link, not its `Apply` link), and reads details from the right-side description pane; stops and prompts for sign-in if redirected to the login page |

## Alternative AI Tools

For richer LLM-based attribute extraction, consider:

| Tool / Model | How to use |
|---|---|
| **OpenAI GPT-4o** | Replace the regex extractors in `extractors/base.py` with a call to the OpenAI Chat Completions API. Send the raw job description text and ask it to return JSON with the required attributes. |
| **Anthropic Claude 3.5 Sonnet** | Same pattern — pipe job text into a Claude prompt asking for structured extraction. Excellent at reasoning about salary ranges stated in non-standard prose. |
| **LangChain + any LLM** | Use LangChain's `WebBaseLoader` + an extraction chain to scrape and parse in one pipeline. Simplifies site-specific handling. |
| **Playwright + AI SDK** | Microsoft's Playwright MCP server can be driven by an LLM agent to handle complex JS-heavy pages better than Selenium. |
| **Bright Data / ScrapingBee** | Proxy-based scraping APIs that handle bot-detection on LinkedIn, reducing need for manual Selenium cookie handling. |
