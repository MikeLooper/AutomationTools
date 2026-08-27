# On-Demand Job Scraper

Reads the job posting currently open in your system browser, scrapes it, and
prints a summary — no URL lists, no launching a separate automated browser.

Loosely based on [`job-search-python`](../job-search-python), but inverted:
instead of driving a fresh, logged-out Selenium browser to a list of search
URLs, this tool looks at whatever single page you already have open. For
public job boards that's enough on its own; for anything login-walled, see
"Enabling the authenticated read" below for what it takes to read your real
session instead of an anonymous request.

## How it works

1. **Find the open page.** Windows UI Automation reads the address bar of
   your foreground Chrome, Edge, or Firefox window to get the URL — this is
   instant and needs no special setup. If more than one browser window is
   open, you'll be asked to pick the right one.
2. **Fetch the page.**
   - If a Chrome/Edge instance is already running with its remote debugging
     port enabled (see below), the tool attaches to that live session and
     reads the exact tab's rendered HTML — cookies and login state included.
   - Otherwise it falls back to a plain, unauthenticated HTTP request. This
     works fine for public job boards; for login-walled pages it prints a
     warning and, when possible, still extracts whatever is publicly
     visible (many boards embed a `schema.org JobPosting` JSON-LD block for
     SEO even on pages that require login to browse).
3. **Determine the site and extract.** The page's hostname is checked
   against a small set of predefined sites (Dice, Greenhouse, LinkedIn,
   Remotive, Connecting Colorado, TopResume). A recognized site uses its
   dedicated extractor (schema.org JSON-LD first, then site-specific CSS
   selectors, then shared text heuristics). An unrecognized site falls back
   to `extractors/generic.py`, which applies the same JSON-LD + heuristic
   approach without any site-specific selectors.
4. **Print a summary**, or **write a report**: a single job-view page prints
   Job Title, Company, Location, Programming Language, Tools, and Salary
   Range to the console. A LinkedIn search-results page with a list of
   cards instead clicks through every card (needs the authenticated read —
   see below, since that's real DOM interaction, not just a fetch), scrapes
   the preview pane after each click, and writes an HTML+JSON report to
   `reports/<timestamp>/`, matching `job-search-python`'s report layout
   (score badges, recommended-jobs summary, the works — see "Settings
   files" for how scoring/exclusion rules plug in, same format as that app).
   The report opens as a new tab in the same dedicated browser this process
   was already attached to (not whatever the OS considers the default
   browser), falling back to `os.startfile` only if that browser isn't
   reachable.

## Enabling the authenticated read (optional)

**This does not work against your normal, everyday Chrome/Edge window.**
Current Chrome/Edge versions refuse to open the remote-debugging port
against your default profile at all — this is deliberate hardening, added
specifically to stop tools like this one from attaching to your real,
logged-in session and reading it out (confirmed by testing: the flag is
silently ignored on the default profile, and works only with a separate
`--user-data-dir`).

To get the authenticated read working, set up a **dedicated Chrome profile**
that you keep logged into the sites you care about, and always launch it
with the debug flag pointed at its own profile folder:

```bash
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\Users\<you>\ChromeAutomationProfile"
```

The first time, log into whatever sites you want readable (LinkedIn, an
internal ATS, etc.) inside that window — the profile folder persists the
session across relaunches, as long as you keep starting it with the same
`--user-data-dir`. Then browse to a job posting in *that* window before
running the tool. `python job_scraper.py` tries port `9222` automatically
(the port in the example above); pass `--debug-port <port>` if you used a
different one.

Without this, the tool still works fine — it just can't see anything behind
a login, and will print a warning saying so instead of failing silently.

## Installation

```bash
pip install -r requirements.txt
```

`pip-system-certs` is included so the plain-HTTP fallback trusts the same
certificates as your OS/corporate network does (needed on machines behind a
TLS-inspecting proxy, where Python's bundled CA list alone gets SSL
verification errors even though the real browser works fine).

## Usage

```bash
python job_scraper.py
```

Or scrape a specific URL directly, bypassing the browser read entirely:

```bash
python job_scraper.py --url "https://remotive.com/remote-jobs/software-dev/example-123456"
```

### Arguments

| Argument | Description |
|---|---|
| `--url` | Job posting URL to use instead of reading the browser's active tab. |
| `--attributes` | Path to the attribute list. Defaults to `settings/attributes.txt`. |
| `--programminglanguages` | Path to programming-language aliases. Defaults to `settings/programminglanguages.txt`. |
| `--tools` | Path to tool aliases. Defaults to `settings/tools.txt`. |
| `--debug-port` | Remote-debugging port of your dedicated browser profile, if not the default `9222`. |

## Settings files

Same format as `job-search-python`:

- `settings/attributes.txt` — one attribute name per line.
- `settings/programminglanguages.txt` / `settings/tools.txt` — one alias per
  line; `discovery:reporting` if the matched term should be reported under a
  different name (e.g. `Amazon Web Services:AWS`).
- `settings/targets.txt` / `settings/exclusions.txt` — only used by the
  LinkedIn list-scrape report, for scoring/filtering jobs (`AttributeName=Value`,
  `AttributeName=Value1 OR Value2`, `Salary Range Includes 200K`). Empty by
  default, which scores every job 100% / recommended — add rules here the
  same way you would in `job-search-python` if you want to filter the report
  down. `--match-pct` (default `75`) sets the recommendation threshold.

## Supported predefined sites

| Site | Notes |
|---|---|
| Dice | Parses the embedded Next.js `__NEXT_DATA__` payload when present. |
| Greenhouse | Reads schema.org JobPosting JSON-LD when the board provides it. |
| LinkedIn | Works on both a direct job-view page and a search-results page with a job open in the preview pane. LinkedIn's CSS classes are hashed/build-generated and not stable, so this reads the `<title>` tag (`"{Job Title} \| {Company} \| LinkedIn"`), an `aria-label="Company, {Name}."` near the logo, and the "About the job" section text instead of any selector. |
| Remotive | — |
| Connecting Colorado | Needs the authenticated read (see above) for most postings. |
| TopResume (Careerio) | — |

Any other domain is handled by `extractors/generic.py`.

## Limitations

- Windows only (uses `uiautomation` for the browser-address-bar read).
- The browser-read step needs a real desktop session — it won't work
  over SSH/RDP without an active console session.
- Firefox support for the address-bar read is best-effort (relies on the
  `urlbar-input` automation ID, which can vary by version).
