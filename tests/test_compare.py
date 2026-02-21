import unittest

from src.compare import build_metrics, generate_comparison_markdown


class TestCompare(unittest.TestCase):
    def test_build_metrics(self):
        current = {
            "w2": [{"box1_wages": 100000.0, "box2_fed_withholding": 15000.0}],
            "brokerage_1099": [{"div_ordinary": 500.0, "int_interest_income": 100.0, "b_summary": {"wash_sales": 50.0}}],
            "form_1098": [{"mortgage_interest_received": 6000.0, "real_estate_taxes": 3000.0}],
        }
        prior = {
            "w2": [{"box1_wages": 90000.0, "box2_fed_withholding": 12000.0}],
            "brokerage_1099": [{"div_ordinary": 450.0, "int_interest_income": 80.0, "b_summary": {"wash_sales": 0.0}}],
            "form_1098": [{"mortgage_interest_received": 6200.0, "real_estate_taxes": 2800.0}],
        }
        metrics = build_metrics(current, prior)
        wages = next(m for m in metrics if m.name == "W-2 total wages (Box 1)")
        self.assertEqual(wages.current, 100000.0)
        self.assertEqual(wages.prior, 90000.0)
        self.assertAlmostEqual(wages.delta or 0, 10000.0)

    def test_generate_markdown_contains_flags(self):
        current = {
            "w2": [{"box1_wages": 120000.0}],
            "brokerage_1099": [],
            "form_1098": [],
        }
        prior = {
            "w2": [{"box1_wages": 80000.0}],
            "brokerage_1099": [],
            "form_1098": [],
        }
        md = generate_comparison_markdown("Kern_Ryan_Brittany_MFJ", 2024, 2023, build_metrics(current, prior))
        self.assertIn("Prior Year Comparison - Kern_Ryan_Brittany_MFJ", md)
        self.assertIn("Large year-over-year change", md)


if __name__ == "__main__":
    unittest.main()
