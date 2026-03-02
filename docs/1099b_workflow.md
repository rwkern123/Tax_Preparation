# 1099-B Focused Workflow (Many-Trade Statements)

This workflow is designed for composite 1099 packets that include dozens/hundreds of trade lines.

## 1) Intake and document controls

1. **Scan and classify** source files as brokerage statements / 1099 composite packets.
2. Build a per-file fingerprint (`sha256`) and retain:
   - client
   - tax year
   - broker name
   - account suffix (if available)
   - source filename + page range
3. Keep all extracted trades linked to the source fingerprint for audit traceability.

## 2) Trade-line extraction target fields

Capture one normalized record per disposition with these fields:

- `description`
- `security_identifier` (CUSIP/ticker/ISIN when present)
- `date_acquired`
- `date_sold_or_disposed`
- `proceeds_gross`
- `cost_basis`
- `wash_sale_code`
- `wash_sale_amount`
- `federal_income_tax_withheld`
- `holding_period` (`short`, `long`, or `unknown`)
- `basis_reported_to_irs` (`covered`, `noncovered`, `unknown`)
- `adjustment_code`
- `adjustment_amount`

### Normalization rules

- Parse currency values into signed decimals (support `$`, commas, and parenthesis negatives).
- Normalize dates to ISO-8601 (`YYYY-MM-DD`).
- Preserve raw row text in `raw_trade_line` when extraction confidence is low.
- If `holding_period` is missing, derive from dates:
  - `<= 365` days: `short`
  - `> 365` days: `long`
- If the statement uses covered/noncovered sections, propagate that section value to each child trade row.

## 3) Durable storage model

Use **two durable outputs** from one canonical trade object set:

### A. Tax-prep export (Form 8949 / Schedule D)

- `1099b_trades_tax.csv` (human review + import-friendly)
- `1099b_trades_tax.jsonl` (line-oriented and auditable)

Suggested columns:

- identity: `client_id`, `tax_year`, `broker_name`, `account_id_suffix`, `source_sha256`, `source_file`, `source_page`
- disposition: `description`, `security_identifier`, `date_acquired`, `date_sold_or_disposed`
- amounts: `proceeds_gross`, `cost_basis`, `adjustment_amount`, `wash_sale_amount`, `federal_income_tax_withheld`
- coding: `holding_period`, `basis_reported_to_irs`, `adjustment_code`, `wash_sale_code`
- derived: `realized_gain_loss`, `form_8949_box`

`form_8949_box` mapping convention:

- `A`: short-term + covered (basis reported)
- `B`: short-term + noncovered
- `C`: short-term + unknown basis reporting
- `D`: long-term + covered
- `E`: long-term + noncovered
- `F`: long-term + unknown basis reporting

### B. Analytics export (future performance dashboard)

- `1099b_trades_analytics.parquet` (preferred)
- fallback `1099b_trades_analytics.csv`

Additional derived fields for analytics:

- `ticker`
- `asset_class` (if available from description mapping)
- `trade_year_month`
- `realized_gain_loss`
- `net_proceeds`
- `wash_disallowed_component`

This structure supports time-series, realized gains by ticker, and broker/account drill-downs.

## 4) Validation and reconciliation gates

Before publishing outputs:

1. **Column completeness gate**: required fields present for each trade row.
2. **Type gate**: dates parse, currency fields parse to decimals.
3. **8949 reasonability gate**: recalc `realized_gain_loss = proceeds_gross - cost_basis + adjustment_amount`.
4. **Statement tie-out gate**:
   - sum of row `proceeds_gross` ~= statement subtotal
   - sum of row `cost_basis` ~= statement subtotal
   - sum of row `wash_sale_amount` ~= statement subtotal
5. **Exception queue**:
   - missing dates
   - unresolved holding period
   - malformed identifier
   - OCR uncertainty

Publish an exceptions file: `1099b_exceptions.csv` for manual cleanup.

## 5) Suggested implementation sequence in this repo

1. Keep current composite-level extraction for high-level checklist support.
2. Add trade-level extraction to produce canonical row objects.
3. Persist both tax and analytics outputs into each client's `_workpapers` folder.
4. Add reconciliation summaries into `Return_Prep_Checklist.md` and follow-up prompts into `Questions_For_Client.md`.
5. Add tests for:
   - date/amount normalization
   - holding-period derivation
   - 8949 box mapping
   - subtotal tie-out behavior

## 6) Canonical JSONL row example

```json
{
  "client_id": "Kern_Ryan_Brittany_MFJ",
  "tax_year": 2024,
  "broker_name": "Fidelity",
  "account_id_suffix": "1234",
  "source_sha256": "...",
  "source_file": "1099 Composite.pdf",
  "source_page": 12,
  "description": "APPLE INC",
  "security_identifier": "AAPL",
  "date_acquired": "2023-02-02",
  "date_sold_or_disposed": "2024-01-29",
  "proceeds_gross": 1050.25,
  "cost_basis": 900.10,
  "wash_sale_code": "W",
  "wash_sale_amount": 20.00,
  "federal_income_tax_withheld": 0.0,
  "holding_period": "long",
  "basis_reported_to_irs": "covered",
  "adjustment_code": "W",
  "adjustment_amount": -20.00,
  "realized_gain_loss": 130.15,
  "form_8949_box": "D"
}
```
