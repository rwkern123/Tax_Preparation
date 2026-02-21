import tempfile
import unittest
from pathlib import Path

from src.organize import OwnerContext, detect_owner_from_name, organize_client_documents


class TestOrganize(unittest.TestCase):
    def test_detect_owner(self):
        context = OwnerContext(
            taxpayer_name="Ryan Kern",
            spouse_name="Brittany Kern",
            spouse_aliases=("Brittany Webb",),
        )
        self.assertEqual(detect_owner_from_name("2024_W2_Ryan_ABC.pdf", context), "Taxpayer")
        self.assertEqual(detect_owner_from_name("2024_1099_Brittany_Webb_Fidelity.pdf", context), "Spouse")
        self.assertEqual(detect_owner_from_name("2024_1098_Mortgage_Joint_WF.pdf", context), "Joint")

    def test_organize_moves_files(self):
        with tempfile.TemporaryDirectory() as td:
            client = Path(td) / "Kern_Ryan_Brittany_MFJ"
            inbox = client / "Inbox"
            inbox.mkdir(parents=True)
            (inbox / "2024_W2_Ryan_ABC.pdf").write_text("dummy", encoding="utf-8")
            (inbox / "2024_1098_Mortgage_Ryan_WF.pdf").write_text("dummy", encoding="utf-8")

            ops = organize_client_documents(
                client,
                OwnerContext(taxpayer_name="Ryan Kern", spouse_name="Brittany Kern"),
                dry_run=False,
            )
            self.assertEqual(len(ops), 2)
            self.assertTrue((client / "01_Taxpayer" / "W2" / "2024_W2_Ryan_ABC.pdf").exists())
            self.assertTrue((client / "01_Taxpayer" / "Form_1098" / "2024_1098_Mortgage_Ryan_WF.pdf").exists())


if __name__ == "__main__":
    unittest.main()
