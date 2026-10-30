# SEC 10-K Data Automation

A cross-platform Python project for fetching SEC Form 10-K filings for a
configurable list of companies and converting filing content to PDF. Configure
the SEC user agent with your own name and contact email before making requests.

## Requirements

- Python 3.10 or later
- pip
- An internet connection

The dependencies include Requests for HTTP, python-dotenv for local
configuration, and Playwright for Chromium-based HTML-to-PDF rendering.

## Setup

Run the commands for your operating system from the project directory.

### Windows

Create and activate a virtual environment in PowerShell:

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
```

In Command Prompt, activate it with:

```bat
py -m venv venv
venv\Scripts\activate.bat
```

If PowerShell prevents activation due to its execution policy, use Command
Prompt or activate the environment using the appropriate policy for your
organization.

### macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

### Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

On Debian-based Linux distributions, install the venv module first if it is
missing (for example, `sudo apt install python3-venv`).

### Install dependencies and configure

With the virtual environment activated, install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Playwright uses a separate Chromium browser download; install it once in each
Python environment before running the application.
On Linux, if Chromium reports missing system libraries, install them with
`python -m playwright install-deps chromium` using the required system
permissions.

Copy `.env.example` to `.env` and replace the example value with your identifying
name and a monitored email address. Configure the companies to process as a
comma-separated list of names:

```text
SEC_USER_AGENT=YourName your.email@domain.com
SEC_COMPANIES=Apple, Meta, Alphabet
```

Keep `.env` local; it is excluded from version control. The SEC expects automated
requests to identify the application and provide contact information. Follow
SEC fair-access guidance and avoid excessive request rates.

## Run

Activate the virtual environment, then run the workflow from the project root:

```bash
python -m src.main
```

Set `SEC_USER_AGENT` and `SEC_COMPANIES` in the environment or `.env` before
running the code. `SEC_COMPANIES` accepts any number of company names separated
by commas. Whitespace is trimmed, empty items are ignored, and duplicate names
are processed once. Names containing commas can be surrounded by double quotes.
For example:

```text
SEC_COMPANIES=Apple, Meta, Alphabet, "Example, Incorporated"
```

You can change this value without editing Python source. The application
matches names against official SEC company titles, resolves their CIKs, fetches
the latest 10-K, and converts it to PDF. Terminal output shows each company's
progress through lookup, download, and PDF rendering, followed by a run summary.

The client retrieves SEC company-title data dynamically and spaces requests to
respect SEC rate limits. Each filing is downloaded and converted to
`output/{Company_Name}_10K.pdf`; company names are sanitized for safe filenames.
The same commands and Python code work on Windows, macOS, and Linux.

Save generated PDFs under `output/`; that directory is ignored by Git. When
finished, leave the virtual environment with:

```bash
deactivate
```

## Project structure and design

```text
quartr-assessment/
├── .env.example          # Template for local environment settings
├── .gitignore            # Excludes local config, generated PDFs, and Python cache
├── README.md             # Setup, usage, and design documentation
├── prompt_log.md         # Representative prompts used during development
├── requirements.txt      # Runtime dependencies
├── requirements-dev.txt  # Runtime dependencies plus pytest
├── output/               # Generated PDFs; created when the tool runs
├── src/
│   ├── main.py           # Configuration, orchestration, and progress logging
│   ├── sec_client.py     # SEC lookup, filing retrieval, and image embedding
│   └── converter.py      # HTML-to-PDF rendering with Playwright
└── tests/
    ├── test_main.py      # Configuration and orchestration tests
    └── test_sec_client.py # SEC filing-selection tests
```

### Responsibilities and data flow

`src/main.py` reads `SEC_COMPANIES`, removes blank and duplicate names, then
processes each company sequentially. `src/sec_client.py` resolves each name to
an SEC CIK, selects the latest exact `10-K`, downloads its primary document,
and embeds SEC-hosted images. `src/converter.py` renders the resulting HTML
with headless Chromium and saves one PDF per company. Keeping these
responsibilities separate makes the SEC integration, workflow, and PDF
conversion easier to understand and test independently.

### Path handling

The application uses `pathlib.Path` for filesystem paths rather than
OS-specific path strings:

- The `.env` file is resolved relative to the project root using the source
  file's location. It is therefore found even when the process is started from
  another working directory.
- The default PDF directory is `output/`, relative to the current working
  directory. Run `python -m src.main` from the project root to use the
  repository's `output/` directory, as shown above. The converter creates the
  directory when needed.
- The temporary HTML and in-progress PDF are created in temporary locations.
  The HTML is written as UTF-8 and cleaned up after rendering; the PDF is
  validated and moved into `output/` only after successful rendering.
- Generated PDFs, `.env`, Python bytecode, and virtual environments are
  excluded from version control by `.gitignore`.

The same path operations work on Windows, macOS, and Linux. The only
platform-specific setup is activating the virtual environment and installing
Chromium's required system libraries where applicable.

## Tests

Install the development dependencies and run the offline unit tests from the
project root:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

The tests mock SEC requests and PDF conversion, so they do not contact the SEC
or require Playwright's Chromium browser.
