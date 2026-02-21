# Tax Return Workpaper Generator (Local-Only MVP)

Offline Python CLI that scans local client folders, classifies tax documents, extracts key fields, and generates workpapers.

## Features
- Local-only processing (no network calls)
- Per-client outputs in `_workpapers/`:
  - `Return_Prep_Checklist.md`
  - `Document_Index.csv`
  - `Data_Extract.json`
  - `Questions_For_Client.md`
  - `Organization_Log.csv` (when `--organize` is used)
- Document support (MVP): PDF, JPG, PNG
- Classification: W-2, brokerage 1099 composite, 1098 mortgage interest, unknown
- Text extraction via embedded PDF text first, optional OCR fallback
- Redaction option for markdown outputs
- Optional auto-organization from a single client intake folder into standardized owner/form subfolders

## Project layout
```
src/
  main.py
  scanner.py
  classify.py
  checklist.py
  questions.py
  models.py
  config.py
  organize.py
  compare.py
  dashboard.py
  webapp.py
  extract/
    generic_pdf.py
    w2.py
    brokerage_1099.py
    form_1098.py
tests/
outputs/
```

## Recommended client folder structure (accuracy-focused)
For best classification and extraction quality, keep one folder per tax return/client unit under the year root.

### Option A: preferred standardized structure
```text
C:\TaxClients\2024\
  Kern_Ryan_Brittany_MFJ\
    01_Taxpayer\
      W2\
      Brokerage_1099\
      Form_1098\
      Other\
    02_Spouse\
      W2\
      Brokerage_1099\
      Form_1098\
      Other\
    03_Joint\
      W2\
      Brokerage_1099\
      Form_1098\
      Other\
    04_Unsorted\
    99_Reference\
      name_aliases.txt
    _workpapers\
```

### Option B: easiest client intake (single drop folder)
If clients upload everything into one place, that is now supported:
```text
C:\TaxClients\2024\
  Kern_Ryan_Brittany_MFJ\
    Inbox\
      all client documents mixed together...
```
Then run with `--organize` and the program will attempt to move documents into the standardized structure.

## Naming conventions to improve accuracy
- Include tax year + form type + owner + institution in filenames.
- Use explicit owner tags: `Ryan`, `Brittany`, or `Joint`.
- For Form 1098 ownership clarity:
  - `2024_1098_Mortgage_Ryan_WellsFargo.pdf` (individual payer)
  - `2024_1098_Mortgage_Joint_WellsFargo.pdf` (joint)
- If spouse has former/alternate names (e.g., Brittany Webb), pass alias flags or store in `99_Reference/name_aliases.txt`.

## Windows setup
1. Create and activate virtual environment:
   - `python -m venv .venv`
   - `.venv\Scripts\activate`
2. Install dependencies:
   - `pip install pdfplumber pypdf pytesseract pillow pdf2image flask`
3. Optional OCR tools:
   - Install **Tesseract OCR** locally and add to PATH.
   - (For OCR on PDFs) install Poppler binaries and add to PATH for `pdf2image`.

## Run
```bash
python -m src.main --root "C:\TaxClients\2024" --year 2024
python -m src.main --root "C:\TaxClients\2024" --year 2024 --ocr --redact --verbose
python -m src.main --root "C:\TaxClients\2024" --year 2024 --client "Kern_Ryan_Brittany_MFJ"
```

### Auto-organize mixed single-folder intake
```bash
python -m src.main --root "C:\TaxClients\2024" --year 2024 \
  --client "Kern_Ryan_Brittany_MFJ" \
  --organize --taxpayer-name "Ryan Kern" --spouse-name "Brittany Kern" --spouse-alias "Brittany Webb"

# preview only (no file moves)
python -m src.main --root "C:\TaxClients\2024" --year 2024 \
  --client "Kern_Ryan_Brittany_MFJ" --organize --organize-dry-run --taxpayer-name "Ryan Kern" --spouse-name "Brittany Kern"
```



### Prior-year comparison report
You can generate a year-over-year comparison using prior-year extracted outputs:
```bash
python -m src.main --root "C:\TaxClients\2024" --year 2024 \
  --compare-prior-year --prior-year-root "C:\TaxClients\2023"
```
This writes `_workpapers/Prior_Year_Comparison.md` per client (when both years have `Data_Extract.json`), with:
- current vs prior values for key metrics (W-2 wages/withholding, 1099 income totals, 1098 mortgage totals)
- delta and percent change
- review flags for large (>20%) year-over-year changes

### Local web UI (client list + follow-up task list)
You can run a local-only dashboard after generating workpapers:
```bash
python -m src.webapp --root "C:\TaxClients\2024" --port 8787
```
Then open `http://127.0.0.1:8787` in your browser.

What you get:
- Client list view with document counts, unknown/error counts, and extracted-form summary.
- Client detail page with follow-up/review tasks from `Questions_For_Client.md`.
- Quick visibility into which clients need attention first.

## Notes on privacy
- The tool is designed for local/offline execution.
- It does not send document text externally.
- `Document_Index.csv` stores metadata + extracted fields only.
- Use `--redact` to mask common PII patterns in markdown outputs.

## Testing
```bash
python -m unittest discover -s tests -p "test_*.py"
```
