import tempfile
import unittest
from pathlib import Path

from src.dashboard import build_client_summary, parse_questions_markdown


class TestDashboard(unittest.TestCase):
    def test_parse_questions_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Questions_For_Client.md"
            p.write_text("# Questions\n\n- First item\n- Second item\n", encoding="utf-8")
            self.assertEqual(parse_questions_markdown(p), ["First item", "Second item"])

    def test_build_client_summary(self):
        with tempfile.TemporaryDirectory() as td:
            client = Path(td) / "Kern_Ryan_Brittany_MFJ"
            wp = client / "_workpapers"
            wp.mkdir(parents=True)

            (wp / "Document_Index.csv").write_text(
                "client,file_path,file_name,sha256,doc_type,confidence,detected_year,issuer,key_fields,extraction_notes\n"
                "A,/a/a.pdf,a.pdf,x,w2,0.9,2024,ABC,{},\n"
                "A,/a/b.pdf,b.pdf,y,unknown,0.1,2024,,,\n",
                encoding="utf-8",
            )
            (wp / "Data_Extract.json").write_text(
                '{"w2":[{}],"brokerage_1099":[],"form_1098":[],"unknown":[{}]}',
                encoding="utf-8",
            )
            (wp / "Questions_For_Client.md").write_text(
                "# Questions\n\n- Need one more document\n", encoding="utf-8"
            )

            summary = build_client_summary(client)
            self.assertTrue(summary.has_outputs)
            self.assertEqual(summary.document_count, 2)
            self.assertEqual(summary.unknown_count, 1)
            self.assertEqual(summary.task_count, 1)
            self.assertEqual(summary.extraction_counts.get("w2"), 1)


if __name__ == "__main__":
    unittest.main()
