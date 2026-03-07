# Tax Preparation Project — Claude Context

## Project Purpose
Local-only Python CLI that scans client tax document folders, classifies documents, extracts key fields, and generates workpapers. No network calls; all processing is offline.

## Tech Stack
- **Language:** Python 3.12
- **PDF extraction:** `pdfplumber`, `pypdf`
- **OCR (optional):** `pytesseract`, `pdf2image` (requires Tesseract + Poppler in PATH)
- **Web UI:** Flask (`src/webapp.py`)
- **Testing:** `unittest` / `pytest`
- **VCS:** Git, hosted on GitHub (`main` branch)

## Project Layout
```
src/
  main.py              # Entry point, CLI arg parsing, orchestration
  scanner.py           # Discovers clients and indexes files
  classify.py          # Classifies documents (W-2, 1099, 1098, unknown)
  models.py            # Dataclasses: DocumentRecord, W2Data, Brokerage1099Data, Brokerage1099Trade, Form1098Data, ExtractionResult
  config.py            # AppConfig dataclass
  checklist.py         # Generates Return_Prep_Checklist.md
  questions.py         # Generates Questions_For_Client.md
  organize.py          # Auto-organizes intake folder into standardized subfolders
  compare.py           # Prior-year YoY comparison report
  dashboard.py         # Data for web UI
  webapp.py            # Flask local web server
  extract/
    generic_pdf.py     # get_document_text() — PDF text + OCR fallback
    w2.py              # parse_w2_text()
    brokerage_1099.py  # parse_brokerage_1099_text()
    form_1099b_trades.py  # parse_1099b_trades_text(), reconciliation, analytics
    form_1098.py       # parse_1098_text()
    text_utils.py      # Shared text helpers
tests/
  test_classify.py
  test_compare.py
  test_dashboard.py
  test_extract_parsers.py
  test_organize.py
  test_1099b_trades.py
docs/
  1099b_workflow.md    # Detailed 1099-B trade extraction workflow
examples/forms/        # Sample PDFs for manual testing (w2/, 1099/, 1098/)
```

## Outputs (written to `<client_dir>/_workpapers/`)
| File | Description |
|---|---|
| `Return_Prep_Checklist.md` | Per-form checklist |
| `Document_Index.csv` | All files with doc_type, confidence, extracted fields |
| `Data_Extract.json` | Structured extraction results (all forms) |
| `Questions_For_Client.md` | Auto-generated follow-up questions |
| `1099b_trades_tax.csv` / `.jsonl` | Trade-level rows for Form 8949/Schedule D |
| `1099b_trades_analytics.csv` | Analytics-ready trade rows |
| `1099b_reconciliation.json` | Reconciliation of trade totals vs. summary |
| `1099b_exceptions.csv` | Flagged trade-level issues |
| `Prior_Year_Comparison.md` | YoY delta report (when `--compare-prior-year`) |
| `Organization_Log.csv` | File move log (when `--organize`) |

## Document Classification Types
- `w2` — W-2 wage statement
- `brokerage_1099` — 1099 composite (DIV, INT, B summary, trade rows)
- `form_1098` — Mortgage interest statement
- `unknown` — Unclassified

## Key CLI Commands
```bash
# Basic run
python -m src.main --root "C:\TaxClients\2024" --year 2024

# Full options
python -m src.main --root "C:\TaxClients\2024" --year 2024 --ocr --redact --verbose

# Single client
python -m src.main --root "C:\TaxClients\2024" --year 2024 --client "Kern_Ryan_Brittany_MFJ"

# Auto-organize intake folder
python -m src.main --root "C:\TaxClients\2024" --year 2024 \
  --client "Kern_Ryan_Brittany_MFJ" \
  --organize --taxpayer-name "Ryan Kern" --spouse-name "Brittany Kern" --spouse-alias "Brittany Webb"

# Dry-run organize (no file moves)
python -m src.main --root "C:\TaxClients\2024" --year 2024 \
  --client "Kern_Ryan_Brittany_MFJ" --organize --organize-dry-run --taxpayer-name "Ryan Kern" --spouse-name "Brittany Kern"

# Prior-year comparison
python -m src.main --root "C:\TaxClients\2024" --year 2024 \
  --compare-prior-year --prior-year-root "C:\TaxClients\2023"

# Web UI (after workpapers generated)
python -m src.webapp --root "C:\TaxClients\2024" --port 8787
```

## Recommended Client Folder Structure
```
C:\TaxClients\2024\
  Kern_Ryan_Brittany_MFJ\
    01_Taxpayer\W2\, Brokerage_1099\, Form_1098\, Other\
    02_Spouse\W2\, Brokerage_1099\, Form_1098\, Other\
    03_Joint\...
    04_Unsorted\
    99_Reference\name_aliases.txt
    _workpapers\
```

## Testing
```bash
python -m unittest discover -s tests -p "test_*.py"
# or
pytest
```

## Design Principles
- **Local-only** — no external API calls, no data leaves the machine
- **OCR-tolerant parsers** — regex patterns handle spacing/formatting inconsistencies from PDF extraction
- `--redact` masks SSNs and EINs in markdown outputs
- `--organize` moves files from a single intake/inbox folder into the standardized subfolder structure
- Prior-year comparison flags >20% YoY changes on key metrics
