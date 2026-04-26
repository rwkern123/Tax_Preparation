# Tax Preparation Tool — Identified Gaps

Gaps identified during codebase review. Last updated: April 2026. Organized by category and approximate priority.

---

## 1. Missing Inbound Form Parsers
Forms that clients receive and bring to their preparer — need extraction support.

| Form | Description | Priority |
|---|---|---|
| ~~**1099-R**~~ | ~~Retirement / IRA / pension distributions~~ | ~~High~~ — **Completed April 2026** |
| ~~**1099-NEC**~~ | ~~Non-employee compensation~~ | ~~High~~ — **Completed April 2026** |
| ~~**Prior Year Form 1040**~~ | ~~Prior-year return parsing (local regex + Azure)~~ | ~~High~~ — **Completed April 2026** |
| ~~**1099-G**~~ | ~~Unemployment compensation, state tax refunds~~ | ~~High~~ — **Completed April 2026** |
| ~~**1099-MISC**~~ | ~~Royalties, rent, prizes, attorney fees~~ | ~~Medium~~ — **Completed April 2026** |
| ~~**1098-T**~~ | ~~Tuition / education credits (AOTC, Lifetime Learning)~~ | ~~Medium~~ — **Completed April 2026** |
| ~~**1099-Q**~~ | ~~Qualified education program (529) distributions~~ | ~~Low~~ — **Completed April 2026** |
| ~~**1099-SA**~~ | ~~HSA / MSA distributions~~ | ~~Low~~ — **Completed April 2026** |
| ~~**SSA-1099**~~ | ~~Social Security benefits~~ | ~~High~~ — **Completed April 2026** |

**Notes:**
- 1099-NEC extractor completed April 2026 — serves as template for remaining forms.
- 1099-R extractor completed April 2026 — dataclass, parser, classifier, `main.py` wiring, checklist section F, questions.
- Prior Year Form 1040 completed April 2026 — `src/extract/prior_year_return.py` (local regex) + `src/extract/azure_prior_year_return.py` (Azure Document Intelligence). Surfaced in client detail UI.
- 1099-G, 1099-MISC, 1098-T, 1099-Q, 1099-SA completed April 2026 — dataclasses, local regex parsers, Azure backup extractors (1099-G/MISC/1098-T use dedicated Azure prebuilt models; 1099-Q/SA use `prebuilt-layout` fallback), classification patterns, and `main.py` wiring. Blank forms copied to `examples/forms/blank_forms/`.
- SSA-1099 is issued by the Social Security Administration, not the IRS — no Azure prebuilt model exists. Will require custom regex parser only.
- Each new form requires: dataclass in `models.py`, extractor in `src/extract/`, classification patterns in `classify.py`, wiring in `main.py`, and checklist/questions entries.

---

## 2. Missing Outbound / Preparation Workflows
Scenarios where the preparer generates a form on behalf of a business-owner client.

| Workflow | Description | Priority |
|---|---|---|
| **1099-NEC prep** | Business client paid contractors $600+; need to issue 1099-NECs | High |
| **1099-MISC prep** | Rent paid to landlords, attorney fees, etc. | Medium |
| **W-9 tracker** | Track which contractors have provided TINs; flag missing W-9s | High |
| **Schedule C from bank statements** | Build a Schedule C for a business client by ingesting business bank/credit-card statements (CSV/OFX/PDF), categorizing transactions into Schedule C expense lines (8–27 + 30 + Part V), summing gross deposits as receipts, and producing a populated ScheduleCData ready for the existing checklist/questions workflow | High |

**Suggested feature:** Contractor intake CSV → validate data → generate filing summary or IRS FIRE-format `.txt` for e-filing.

**Schedule-C-from-bank-statements design notes:**
- Inputs: business bank statement CSV exports (or OFX/QFX), business credit card statements, optional manual journal entries CSV.
- Pipeline: parse statements → dedup transactions across accounts → classify each line into a Schedule C expense bucket via rules + keyword map (e.g., "STAPLES" → line 22 Supplies, "DELTA AIR" → line 24a Travel, recurring same-payee → contract labor candidate) → aggregate to ScheduleCData → flag uncategorized rows for preparer review.
- Outputs: populated `ScheduleCData` (slots into existing `ExtractionResult.schedule_c`), per-category transaction CSV for audit trail, "Uncategorized" CSV for manual mapping, suggested adjustments (personal-use add-backs, owner draws excluded, depreciation deferred to Form 4562 worksheet).
- Reuses: existing Schedule C dataclass, checklist Section F formatting, questions.py Schedule C prompts.
- New components needed: `src/intake/bank_statement_csv.py` (parser per institution/format), `src/intake/transaction_classifier.py` (rules engine + override map), `src/intake/schedule_c_builder.py` (aggregator that fills ScheduleCData), CLI flag `--build-schedule-c <client>` to invoke.

---

## 3. Schedule / Complex Return Support
High-value clients often have complex return items not currently tracked.

| Form / Schedule | Description | Priority |
|---|---|---|
| ~~**Schedule C**~~ | ~~Self-employment income and expenses~~ | ~~High~~ — **Completed April 2026** |
| **K-1 (1065 / 1120S)** | Partnership / S-Corp pass-through income | High |
| **Schedule E** | Rental income, royalties, pass-through | Medium |
| **Form 8949 / Schedule D** | Currently trade-level only; no high-level summary form parsing | Medium |
| **Form 4952** | Investment interest expense deduction | Low |
| **Form 3115** | Accounting method changes | Low |

**Notes:**
- Schedule C completed April 2026 — `ScheduleCData` dataclass (full Parts I–V coverage), `src/extract/schedule_c.py` (local regex parser handling two-column form layout with subletter-only line markers), `src/extract/azure_schedule_c.py` (Azure `prebuilt-layout` fallback), classification patterns, `main.py` wiring with Azure escalation, new "Section F — Schedule C" in `checklist.py` with audit-flag triggers (loss + at-risk box, depreciation/Form 4562, home office method, vehicle evidence, line I/J 1099 filing gap, line H start-up election, line G material participation), `questions.py` Schedule C prompts, blank Schedule C PDF copied to `examples/forms/blank_forms/f1040sc.pdf`, `tests/test_schedule_c.py` (10 tests covering header, all four parts, classification, loss/at-risk, blank-form low-confidence). Renumbered checklist sections G–K to make room.

---

## 4. Data Quality / Validation Gaps

- **No deduplication detection** — same document uploaded twice will double-count income.
- **No post-extraction validation pass** — impossible values (negative wages, wash sales > proceeds) are logged but not surfaced to the preparer in a structured way.
- **No cross-form consistency checks** — e.g., W-2 Box 1 totals vs. prior-year Form 1040 Line 1a.
- **OCR threshold is hardcoded** at <120 characters; some partially-scanned PDFs pass the threshold but are still unreadable.

---

## 5. Broker / Issuer Coverage

- **Brokerage CSV/XML parsers added** (`brokerage_1099_csv.py`, `brokerage_1099_xml.py`) — April 2026. Coverage is currently Schwab-centric.
- **Fidelity, E*TRADE, Interactive Brokers, TD Ameritrade** exports still won't parse correctly.
- **No OFX support beyond TAX1099 format** — other OFX variants unsupported.

Suggested approach: abstract a broker adapter interface; implement per-broker adapters as needed.

---

## 6. Web UI / Dashboard Gaps

- **No manual override / correction UI** — preparer cannot correct an extracted value in the browser.
- **No Excel/CSV export** from the dashboard for downstream tax software import.
- **Dashboard rebuilds from scratch** on every page load — no caching of JSON/CSV summaries.
- **No authentication** — acceptable for local-only use, but worth noting if ever exposed on a network.
- ~~**No prior-year comparison visible in UI**~~ — **Completed April 2026**: prior-year return data is now surfaced on the client detail page.

---

## 7. Multi-State / Complex Filing Scenarios

- Questions.py flags multi-state W-2 situations, but there is no structured extraction or checklist support for:
  - Apportioned income across states
  - Nonresident state returns
  - State-level K-1 adjustments

---

## 8. Performance / Scalability

- **Single-threaded serial processing** — slow for large batches (20+ clients, many PDFs each).
- **No caching of extracted text or results** — every run re-processes all PDFs from scratch.

---

## 9. Documentation Gaps

- **Azure setup guide incomplete** — Azure Document Intelligence endpoint/API key acquisition and configuration steps not fully documented. (Azure extractors exist for W-2, brokerage 1099-B, 1098, 1099-G, 1099-MISC, 1098-T, 1099-Q, 1099-SA, and prior-year Form 1040 — but onboarding a new user requires undocumented setup.)
- **OCR setup on Windows** — Tesseract + Poppler PATH configuration not documented.
- **No troubleshooting guide** for common parse failures (low-confidence extractions, blank fields).
