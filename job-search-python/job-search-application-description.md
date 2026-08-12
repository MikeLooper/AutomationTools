# Job Search Agent - Application Logic & Architecture

## Overview
The **Job Search Agent** is a Python-based application that automates job searches across multiple job boards, extracts relevant job information, matches jobs against user-defined criteria, and generates HTML/JSON reports with scoring and recommendations.

---

## Core Components

### 1. **Main Entry Point** (`job-search`)
The orchestrator that ties everything together:

- **Load Configuration Files**
  - `settings/urls.txt` - List of job search URLs to scrape (supports comments with `#`)
  - `settings/attributes.txt` - Which job attributes to extract (e.g., Job Title, Programming Language, Tools, Salary Range)
  - `settings/targets.txt` - Matching rules to score jobs
  - `settings/programminglanguages.txt` - Programming-language discovery/reporting aliases
  - `settings/tools.txt` - Tool discovery/reporting aliases

- **Process Flow**
  1. For each URL:
  - Detect the job board (Connecting Colorado, Dice, LinkedIn, GlassDoor, Greenhouse, Remotive, or generic)
     - Launch site-specific Selenium extractor
     - Extract all jobs and requested attributes
    2. Optionally trim each URL result set to `--max-jobs-per-url` jobs (0 means no limit)
    3. Score each job against target rules
    4. Calculate match percentage (number of matched rules / total rules × 100)
    5. Flag jobs as "RECOMMENDED" if match % ≥ minimum threshold (default: 75%)
    6. Generate timestamped report directory with:
     - `report.html` - Interactive visual report
     - `report.json` - Raw data for programmatic access
    7. Auto-open HTML report in default browser

- **Command-Line Arguments**
  - `--urls` - Path to URLs file (default: `settings/urls.txt`)
  - `--attributes` - Path to attributes file (default: `settings/attributes.txt`)
  - `--targets` - Path to targets file (default: `settings/targets.txt`)
  - `--programminglanguages` - Path to language aliases file (default: `settings/programminglanguages.txt`)
  - `--tools` - Path to tools aliases file (default: `settings/tools.txt`)
  - `--match-pct` - Minimum recommendation threshold 0-100 (default: 75)
  - `--max-jobs-per-url` - Maximum jobs processed per URL; `0` means no limit (default: 0)

---

### 2. **Site-Specific Extractors** (`extractors/` directory)

**Base Extractor** (`base.py`)
- Provides Selenium Chrome WebDriver setup with anti-detection measures
- Implements attribute extraction helpers for common job fields
- Supports headless and headful (visible) browser modes

**Extractor Types:**

| Site | Class | Notes |
|------|-------|-------|
| jobs.connectingcolorado.gov | `ConnectingColoradoExtractor` | Clicks each left-side job card and extracts description from right-side detail pane |
| Dice.com | `DiceExtractor` | Standard Selenium scraping |
| Glassdoor | `GlassdoorExtractor` | Handles dynamic content |
| Greenhouse.io | `GreenhouseExtractor` | ATS job board |
| LinkedIn | `LinkedInExtractor` | **Non-headless required** (login walls) |
| Remotive | `RemotiveExtractor` | Remote job specialization |
| Unknown | `GenericExtractor` | Fallback with heuristic CSS selectors |

**Dispatcher** (`dispatcher.py`)
- Routes URLs to appropriate extractor by domain
- Returns `GenericExtractor()` for unrecognized sites

**Attribute Extraction Helpers:**
- **Job Title**: Regex patterns or first non-empty line
- **Programming Language**: Uses `settings/programminglanguages.txt` aliases as the source of truth
- **Tools**: Uses `settings/tools.txt` aliases as the source of truth
- **Salary Range**: Extracts patterns like "$100,000 - $200,000", "100K–200K", "Up to $300K", "$150K+"

**Alias Parsing Rules:**
- A line without a colon uses the same value for discovery and reporting
- A line with a colon uses `discovery:reporting`
- For tool aliases, only the first colon is treated as the separator

---

### 3. **Matcher** (`matcher.py`)
Evaluates how well extracted job attributes match user-defined target rules.

**Supported Rule Formats:**

1. **Exact Attribute Match**
   ```
   AttributeName=Value
   ```
   - Case-insensitive substring match
   - Example: `Job Title=Senior Engineer`

2. **Multiple Options (OR)**
   ```
   AttributeName=Value1 OR Value2 OR Value3
   ```
   - Matches if ANY option is found in extracted attribute
   - Example: `Programming Language=C# OR .NET OR Java`

3. **Salary Range Inclusion**
   ```
   Salary Range Includes <amount>
   ```
   - Validates if job's salary range spans the specified amount
   - Amount formats: `200000`, `200K`, `$200K`, `$200,000`
   - Handles ranges like "$150K–$250K", "Up to $300K", "$200K+"
   - Example: `Salary Range Includes 200K` (checks if job salary includes $200,000)

**Matching Algorithm:**
- For each target rule:
  - Parse and evaluate against extracted attributes
  - Mark as matched/unmatched
  - Track details (rule, matched status, extracted value)
- Calculate score: `(matched_count / total_rules) × 100`
- Return percentage score and detailed match breakdown

---

### 4. **Reporter** (`reporter.py`)
Generates visual HTML reports using Jinja2 templates.

- Takes scored results and renders interactive report
- Displays:
  - Timestamp of report generation
  - Minimum match % threshold used
  - Total jobs found vs. recommended count
  - Per-job scoring details and match rules
  - Source URLs and job links
- Outputs:
  - `report.html` (auto-opened in browser)
  - `report.json` (raw data export)

---

## Workflow Example

### **Scenario: Find C# Developer Jobs**

#### Step 1: Create `settings/urls.txt`
```
# Remote C# jobs from Dice
https://www.dice.com/jobs?q=C%23&filters.workplaceTypes=Remote

# C# positions on LinkedIn
https://www.linkedin.com/jobs/search/?keywords=C%23

# .NET jobs on Remotive
https://remotive.com/remote-jobs?query=%22.net%22
```

#### Step 2: Create `settings/attributes.txt`
```
Job Title
Programming Language
Tools
Salary Range
```

#### Step 3: Create `settings/programminglanguages.txt` and `settings/tools.txt`
```
# programminglanguages.txt
C#
.NET
Java
Python
JavaScript

# tools.txt
Amazon Web Services:AWS
Google Cloud Platform:GCP
Model Context Protocol:MCP
CI/CD
```

#### Step 4: Create `settings/targets.txt`
```
# Target rules for scoring
Programming Language=C# OR .NET
Job Title=Developer OR Engineer OR Architect
Salary Range Includes 120K
```

#### Step 5: Run the Agent
```bash
python job-search \
  --urls settings/urls.txt \
  --attributes settings/attributes.txt \
  --targets settings/targets.txt \
  --programminglanguages settings/programminglanguages.txt \
  --tools settings/tools.txt \
  --match-pct 70 \
  --max-jobs-per-url 25
```

#### Step 6: Output
- **Dice.com**: Finds 45 C# developer jobs, ~70% match rate on average
- **LinkedIn**: Finds 32 positions, 15% blocked by login walls
- **Remotive**: Finds 28 remote .NET roles, 85% match rate
- **Report**: Generated at `reports/2026-08-07_21-10/`
  - 23 jobs recommended (≥70% match)
  - HTML report with color-coded matches
  - JSON export with all raw data

---

## Configuration Examples

### Example 1: Full-Stack Role with Experience Requirements
```
# settings/urls.txt
https://www.dice.com/jobs?q=Full+Stack&filters.experienceLevel=Senior
https://www.linkedin.com/jobs/search/?keywords=full%20stack

# settings/attributes.txt
Job Title
Programming Language
Tools
Salary Range

# settings/programminglanguages.txt
JavaScript
TypeScript
ReactJS:React
Node.js
Java
Python

# settings/tools.txt
Amazon Web Services:AWS
Google Cloud Platform:GCP
Kubernetes
Docker

# settings/targets.txt
Job Title=Full Stack
Programming Language=JavaScript OR TypeScript OR React
Programming Language=Java OR Python OR Node.js
Tools=AWS OR Kubernetes OR Docker
Salary Range Includes 150K
```

### Example 2: Solutions Architect in Denver
```
# settings/urls.txt
https://www.dice.com/jobs?q=Solutions+Architect&location=Denver%2C+CO
https://www.glassdoor.com/Job/denver-solutions-architect-jobs

# settings/attributes.txt
Job Title
Programming Language
Tools
Salary Range

# settings/programminglanguages.txt
Java
C#
Python

# settings/tools.txt
Azure
Amazon Web Services:AWS
GCP

# settings/targets.txt
Job Title=Solutions Architect OR Principal Architect
Programming Language=Java OR C# OR Python
Tools=Azure OR AWS OR GCP
Salary Range Includes 200K
```

### Example 3: Remote DevOps Position
```
# settings/urls.txt
https://remotive.com/remote-jobs?query=DevOps&employment-type=full-time

# settings/attributes.txt
Job Title
Programming Language
Tools

# settings/programminglanguages.txt
Python
Go
Rust

# settings/tools.txt
CI/CD
CloudWatch
Kubernetes
Linux

# settings/targets.txt
Job Title=DevOps OR Platform Engineer
Programming Language=Python OR Go OR Rust
Tools=CI/CD OR Kubernetes OR Linux
```

---

## Key Features

✅ **Multi-Site Support** - Seamlessly extract from Connecting Colorado, Dice, LinkedIn, GlassDoor, Greenhouse, Remotive, or any site  
✅ **Intelligent Extraction** - Automatically identifies job titles, technologies, and salary ranges  
✅ **Flexible Matching** - Supports exact matches, OR logic, and complex salary range validation  
✅ **Anti-Detection** - Masks browser automation to bypass bot detection  
✅ **Batch Processing** - Process 100+ URLs in one run  
✅ **Rich Reporting** - HTML visualization + JSON export  
✅ **Extensible Extractors** - Add new job boards by creating a new extractor class  
✅ **Configuration-Driven Extraction** - Programming Language and Tools are driven by alias files, not hard-coded lists  

---

## File Structure
```
job-search/
├── job-search                   # Main entry point
├── matcher.py                   # Job scoring logic
├── reporter.py                  # Report generation
├── settings/
│   ├── urls.txt                 # Search URLs (config)
│   ├── attributes.txt           # Extraction targets (config)
│   ├── targets.txt              # Matching rules (config)
│   ├── programminglanguages.txt # Language aliases (discovery/reporting)
│   └── tools.txt                # Tool aliases (discovery/reporting)
├── requirements.txt             # Python dependencies
├── extractors/
│   ├── base.py                  # Base class + helpers
│   ├── dispatcher.py            # URL → Extractor routing
│   ├── linkedin.py              # LinkedIn-specific
│   ├── dice.py                  # Dice-specific
│   ├── glassdoor.py             # GlassDoor-specific
│   ├── greenhouse.py            # Greenhouse-specific
│   ├── remotive.py              # Remotive-specific
│   └── generic.py               # Fallback extractor
└── templates/
    └── report.html.j2           # HTML report template
```

---

## Dependencies
- **Selenium** - Browser automation
- **WebDriver Manager** - Chrome driver management
- **Jinja2** - Template rendering
- **Python 3.10+** - Modern syntax (type hints)

---

## Notes

1. **LinkedIn requires non-headless mode** due to aggressive bot detection
2. **Salary extraction** uses regex; ambiguous formats may be missed
3. **Generic extractor** uses CSS class heuristics; may miss jobs on non-standard sites
4. **Selenium drivers** auto-managed but require Chrome/Chromium installed
5. **Report timestamps** use format: `YYYY-MM-DD_HH-MM` (note leading "1" for sorting)
6. **Alias-based extraction**: `programminglanguages.txt` and `tools.txt` support `discovery:reporting` values; if no colon is present, the same value is used for both
