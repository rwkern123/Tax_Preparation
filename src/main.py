from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

from src.checklist import generate_checklist
from src.classify import classify_document
from src.config import AppConfig
from src.extract.brokerage_1099 import parse_brokerage_1099_text
from src.extract.form_1099b_trades import (
    build_trade_exceptions,
    parse_1099b_trades_text,
    summarize_trade_reconciliation,
    trade_to_analytics_row,
    trade_to_tax_row,
)
from src.extract.form_1098 import parse_1098_text
from src.extract.generic_pdf import get_document_text
from src.extract.w2 import parse_w2_text
from src.compare import build_metrics, generate_comparison_markdown, load_extract
from src.models import DocumentRecord, ExtractionResult
from src.organize import OwnerContext, organize_client_documents
from src.questions import generate_questions
from src.scanner import discover_clients, index_client_files


def maybe_redact(text: str, enabled: bool) -> str:
    if not enabled:
        return text
    import re

    text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "XXX-XX-XXXX", text)
    text = re.sub(r"\b\d{2}-\d{7}\b", "XX-XXXXXXX", text)
    return text





def maybe_generate_prior_year_comparison(client_dir: Path, out_dir: Path, config: AppConfig) -> None:
    if not config.compare_prior_year or not config.prior_year_root:
        return
    prior_client_dir = config.prior_year_root / client_dir.name
    current_extract = load_extract(out_dir / "Data_Extract.json")
    prior_extract = load_extract(prior_client_dir / "_workpapers" / "Data_Extract.json")
    if not current_extract or not prior_extract:
        return

    prior_year = config.tax_year - 1
    metrics = build_metrics(current_extract, prior_extract)
    report = generate_comparison_markdown(client_dir.name, config.tax_year, prior_year, metrics)
    (out_dir / "Prior_Year_Comparison.md").write_text(report, encoding="utf-8")

def _write_1099b_trade_outputs(client_dir: Path, out_dir: Path, config: AppConfig, extraction: ExtractionResult) -> None:
    if not extraction.brokerage_1099_trades:
        return

    import csv

    tax_rows = [trade_to_tax_row(client_dir.name, config.tax_year, t) for t in extraction.brokerage_1099_trades]
    analytics_rows = [trade_to_analytics_row(client_dir.name, config.tax_year, t) for t in extraction.brokerage_1099_trades]

    stated_proceeds = sum((b.b_summary.get("proceeds") or 0.0) for b in extraction.brokerage_1099) or None
    stated_cost_basis = sum((b.b_summary.get("cost_basis") or 0.0) for b in extraction.brokerage_1099) or None
    stated_wash_sales = sum((b.b_summary.get("wash_sales") or 0.0) for b in extraction.brokerage_1099) or None
    reconciliation = summarize_trade_reconciliation(
        extraction.brokerage_1099_trades,
        stated_proceeds=stated_proceeds,
        stated_cost_basis=stated_cost_basis,
        stated_wash_sales=stated_wash_sales,
    )

    exceptions = build_trade_exceptions(extraction.brokerage_1099_trades, reconciliation)

    tax_fields = list(tax_rows[0].keys())
    with (out_dir / "1099b_trades_tax.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=tax_fields)
        writer.writeheader()
        writer.writerows(tax_rows)

    with (out_dir / "1099b_trades_tax.jsonl").open("w", encoding="utf-8") as f:
        for row in tax_rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")

    analytics_fields = list(analytics_rows[0].keys())
    with (out_dir / "1099b_trades_analytics.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=analytics_fields)
        writer.writeheader()
        writer.writerows(analytics_rows)

    with (out_dir / "1099b_reconciliation.json").open("w", encoding="utf-8") as f:
        json.dump(reconciliation, f, indent=2, sort_keys=True)

    with (out_dir / "1099b_exceptions.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["source_file", "description", "issue"])
        writer.writeheader()
        writer.writerows(exceptions)


def process_client(client_dir: Path, config: AppConfig) -> None:
    out_dir = client_dir / "_workpapers"
    out_dir.mkdir(exist_ok=True)

    if config.organize:
        ops = organize_client_documents(
            client_dir,
            OwnerContext(
                taxpayer_name=config.taxpayer_name,
                spouse_name=config.spouse_name,
                spouse_aliases=config.spouse_aliases,
            ),
            dry_run=config.organize_dry_run,
        )
        with (out_dir / "Organization_Log.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["source", "destination", "doc_type", "owner"])
            writer.writeheader()
            writer.writerows(ops)

    extraction = ExtractionResult()
    records: list[DocumentRecord] = []

    for row in index_client_files(client_dir):
        path = Path(row["file_path"])
        try:
            text, notes = get_document_text(path, config.enable_ocr)
            doc_type, confidence, detected_year = classify_document(path, text)

            key_fields = {}
            issuer = None
            if doc_type == "w2":
                parsed = parse_w2_text(text)
                extraction.w2.append(parsed)
                key_fields = asdict(parsed)
                issuer = parsed.employer_name
            elif doc_type == "brokerage_1099":
                parsed = parse_brokerage_1099_text(text)
                extraction.brokerage_1099.append(parsed)
                trades = parse_1099b_trades_text(text, parsed.broker_name, path.name, row["sha256"])
                extraction.brokerage_1099_trades.extend(trades)
                key_fields = asdict(parsed)
                key_fields["trade_count"] = len(trades)
                issuer = parsed.broker_name
            elif doc_type == "form_1098":
                parsed = parse_1098_text(text)
                extraction.form_1098.append(parsed)
                key_fields = asdict(parsed)
                issuer = parsed.lender_name
            else:
                extraction.unknown.append({"file_name": path.name, "reason": "Unclassified"})

            records.append(
                DocumentRecord(
                    client=client_dir.name,
                    file_path=str(path),
                    file_name=path.name,
                    sha256=row["sha256"],
                    doc_type=doc_type,
                    confidence=confidence,
                    detected_year=detected_year,
                    issuer=issuer,
                    key_fields=key_fields,
                    extraction_notes=notes,
                )
            )
        except Exception as exc:
            records.append(
                DocumentRecord(
                    client=client_dir.name,
                    file_path=str(path),
                    file_name=path.name,
                    sha256=row["sha256"],
                    doc_type="error",
                    confidence=0.0,
                    extraction_notes=[f"processing_error:{type(exc).__name__}"],
                )
            )

    with (out_dir / "Document_Index.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["client", "file_path", "file_name", "sha256", "doc_type", "confidence", "detected_year", "issuer", "key_fields", "extraction_notes"],
        )
        writer.writeheader()
        for rec in records:
            row_out = asdict(rec)
            row_out["key_fields"] = json.dumps(row_out["key_fields"], sort_keys=True)
            row_out["extraction_notes"] = ";".join(row_out["extraction_notes"])
            writer.writerow(row_out)

    with (out_dir / "Data_Extract.json").open("w", encoding="utf-8") as f:
        json.dump(extraction.to_dict(), f, indent=2, sort_keys=True)

    checklist = maybe_redact(generate_checklist(client_dir.name, extraction), config.redact)
    questions = maybe_redact(generate_questions(client_dir.name, extraction), config.redact)

    (out_dir / "Return_Prep_Checklist.md").write_text(checklist, encoding="utf-8")
    (out_dir / "Questions_For_Client.md").write_text(questions, encoding="utf-8")
    _write_1099b_trade_outputs(client_dir, out_dir, config, extraction)
    maybe_generate_prior_year_comparison(client_dir, out_dir, config)


def parse_args() -> AppConfig:
    p = argparse.ArgumentParser(description="Local-only tax return workpaper generator")
    p.add_argument("--root", required=True, help="Root folder with client subfolders")
    p.add_argument("--year", required=True, type=int, help="Tax year (e.g. 2024)")
    p.add_argument("--ocr", action="store_true", help="Enable OCR fallback")
    p.add_argument("--redact", action="store_true", help="Redact PII in markdown outputs")
    p.add_argument("--client", help="Process only one client folder")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--organize", action="store_true", help="Auto-organize source docs into standardized owner/form subfolders")
    p.add_argument("--organize-dry-run", action="store_true", help="Preview organization plan without moving files")
    p.add_argument("--taxpayer-name", help="Taxpayer full name for owner tagging during organization")
    p.add_argument("--spouse-name", help="Spouse full name for owner tagging during organization")
    p.add_argument("--spouse-alias", action="append", default=[], help="Spouse alias/former name, repeatable")
    p.add_argument("--compare-prior-year", action="store_true", help="Generate prior-year comparison report when prior-year outputs are available")
    p.add_argument("--prior-year-root", help="Root folder containing prior-year client directories")
    args = p.parse_args()
    return AppConfig(
        root=Path(args.root),
        tax_year=args.year,
        enable_ocr=args.ocr,
        redact=args.redact,
        client_filter=args.client,
        verbose=args.verbose,
        organize=args.organize,
        organize_dry_run=args.organize_dry_run,
        taxpayer_name=args.taxpayer_name,
        spouse_name=args.spouse_name,
        spouse_aliases=tuple(args.spouse_alias),
        compare_prior_year=args.compare_prior_year,
        prior_year_root=Path(args.prior_year_root) if args.prior_year_root else None,
    )


def main() -> None:
    config = parse_args()
    clients = discover_clients(config.root, config.client_filter)
    for client_dir in clients:
        process_client(client_dir, config)
        if config.verbose:
            print(f"Processed {client_dir}")


if __name__ == "__main__":
    main()
