# Tax Preparation Portals

A local-first tax preparation system with two user-facing Flask applications:

- **Client portal** — registration, two-factor authentication, questionnaires,
  document intake, and Schedule C interviews.
- **Preparer portal** — client review, document parsing, field overrides, tax
  estimates, Schedule C review, and federal return PDF generation.

The reusable parsing and calculation engine lives in `src/`. It is application
code shared by the portals, not a separate command-line product.

## Supported document extraction

- W-2
- Brokerage 1099 composites and 1099-B trades (PDF, supported CSV, and XML)
- Forms 1098 and 1098-T
- Forms 1099-NEC, 1099-R, 1099-G, 1099-MISC, 1099-Q, and 1099-SA
- SSA-1099
- Prior-year Form 1040
- Schedule C

PDF text is parsed locally. OCR is optional. Azure Document Intelligence is an
explicit opt-in fallback for supported low-confidence documents.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Optional OCR requires Tesseract and Poppler installed on the computer.

Before using the preparer portal, set persistent credentials:

```powershell
$env:PREPARER_PASSWORD = "choose-a-strong-password"
$env:PREPARER_SECRET_KEY = "a-long-random-secret"
$env:PORTAL_SECRET_KEY = "a-different-long-random-secret"
```

Do not expose either development server directly to a public network.

## Run

Client portal:

```powershell
python run_portal.py
```

Open `http://127.0.0.1:5050`.

Preparer portal:

```powershell
python run_preparer.py
```

Open `http://127.0.0.1:8800`. On Windows, `launch_portal.bat` and
`launch_preparer.bat` provide shortcuts.

## Project layout

```text
portal/       Client portal
preparer/     Preparer portal
src/          Shared classifiers, extractors, models, and tax calculations
pdf_forms/    Blank IRS PDF assets used by return generation
portal_data/  Local SQLite databases and uploads (ignored; contains PII)
tests/        Shared-engine tests
```

## Data and privacy

Client documents and databases stay under `portal_data/` and must never be
committed. The repository's example tax documents should contain only synthetic
or appropriately redacted data. Enabling Azure sends selected documents to that
external service for extraction.

## Tests

```powershell
python -m pytest -q
```

See `ideas/roadmap.md` for known limitations and planned work.
