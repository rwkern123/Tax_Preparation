import unittest

from src.extract.form_1099b_trades import (
    build_trade_exceptions,
    parse_1099b_trades_text,
    summarize_trade_reconciliation,
    trade_to_tax_row,
)


class Test1099BTrades(unittest.TestCase):
    def test_parse_trade_lines_and_context(self):
        text = """
        Form 1099-B
        Short-Term Transactions for which basis is reported to the IRS
        APPLE INC (AAPL) 01/02/2024 02/01/2024 1,050.25 900.10 20.00
        MICROSOFT CORP (MSFT) 01/03/2023 02/10/2024 2,000.00 1,500.00
        """
        trades = parse_1099b_trades_text(text, "Fidelity", "sample.pdf", "abc123")
        self.assertEqual(len(trades), 2)
        self.assertEqual(trades[0].security_identifier, "AAPL")
        self.assertEqual(trades[0].holding_period, "short")
        self.assertEqual(trades[0].basis_reported_to_irs, "covered")
        self.assertEqual(trades[0].form_8949_box, "A")
        self.assertAlmostEqual(trades[0].adjustment_amount, -20.00)
        self.assertEqual(trades[1].holding_period, "short")

    def test_derive_holding_period_when_context_missing(self):
        text = """
        TESLA INC TSLA 01/02/2023 02/10/2024 2,000.00 1,200.00
        """
        trades = parse_1099b_trades_text(text, "Schwab", "s.pdf", "hash")
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].holding_period, "long")
        self.assertEqual(trades[0].form_8949_box, "F")
        self.assertEqual(trades[0].security_identifier, "TSLA")

    def test_tax_row_and_exceptions(self):
        text = """
        Long-Term Transactions for which basis is not reported to the IRS
        INDEX FUND (VTI) 01/02/2020 03/11/2024 10,000.00 7,000.00
        """
        trade = parse_1099b_trades_text(text, "Vanguard", "f.pdf", "h1")[0]
        row = trade_to_tax_row("Client_A", 2024, trade)
        self.assertEqual(row["client_id"], "Client_A")
        self.assertEqual(row["tax_year"], 2024)
        self.assertEqual(row["form_8949_box"], "E")

        exceptions = build_trade_exceptions([trade])
        self.assertEqual(exceptions, [])

    def test_reconciliation_and_exception_on_large_delta(self):
        text = """
        Short-Term Transactions for which basis is reported to the IRS
        ABC CO (ABC) 01/02/2024 03/01/2024 1,000.00 800.00 10.00
        """
        trades = parse_1099b_trades_text(text, "Broker", "x.pdf", "sha")
        rec = summarize_trade_reconciliation(
            trades,
            stated_proceeds=900.00,
            stated_cost_basis=700.00,
            stated_wash_sales=0.0,
        )
        self.assertEqual(rec["parsed_proceeds"], 1000.00)
        self.assertEqual(rec["proceeds_delta"], 100.00)

        exceptions = build_trade_exceptions(trades, rec)
        self.assertTrue(any(e["issue"].startswith("proceeds_delta") for e in exceptions))


if __name__ == "__main__":
    unittest.main()
