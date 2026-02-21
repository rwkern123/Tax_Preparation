import unittest
from pathlib import Path

from src.classify import classify_document


class TestClassify(unittest.TestCase):
    def test_classify_w2(self):
        doc_type, confidence, year = classify_document(
            Path("My_W2_2024.pdf"),
            "Form W-2 Wage and Tax Statement 2024",
        )
        self.assertEqual(doc_type, "w2")
        self.assertGreaterEqual(confidence, 0.35)
        self.assertEqual(year, 2024)

    def test_classify_brokerage(self):
        doc_type, confidence, _ = classify_document(
            Path("fidelity_composite.pdf"),
            "1099-DIV 1099-INT 1099-B composite statement",
        )
        self.assertEqual(doc_type, "brokerage_1099")
        self.assertGreaterEqual(confidence, 0.35)

    def test_classify_1098(self):
        doc_type, confidence, _ = classify_document(
            Path("2024_1098_Mortgage_Ryan_WellsFargo.pdf"),
            "Form 1098 Mortgage Interest Statement",
        )
        self.assertEqual(doc_type, "form_1098")
        self.assertGreaterEqual(confidence, 0.35)


if __name__ == "__main__":
    unittest.main()
