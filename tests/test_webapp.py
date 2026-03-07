import tempfile
import unittest
from pathlib import Path

from src.webapp import create_app


def _make_client(root: Path, name: str) -> Path:
    """Create a minimal client folder with workpapers."""
    client = root / name
    wp = client / "_workpapers"
    wp.mkdir(parents=True)

    (wp / "Document_Index.csv").write_text(
        "client,file_path,file_name,sha256,doc_type,confidence,detected_year,issuer,key_fields,extraction_notes\n"
        "A,/a/w2.pdf,w2.pdf,abc,w2,0.95,2024,ACME,{},\n"
        "A,/a/unk.pdf,unk.pdf,def,unknown,0.1,2024,,,\n",
        encoding="utf-8",
    )
    (wp / "Data_Extract.json").write_text(
        '{"w2":[{}],"brokerage_1099":[],"form_1098":[],"unknown":[{}]}',
        encoding="utf-8",
    )
    (wp / "Questions_For_Client.md").write_text(
        "# Questions\n\n- Missing W-2 box 12\n- Confirm mortgage payoff\n",
        encoding="utf-8",
    )
    return client


class TestWebApp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _make_client(self.root, "TestClient_A")
        _make_client(self.root, "TestClient_B")
        app = create_app(self.root)
        app.config["TESTING"] = True
        self.client = app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    # --- index route ---

    def test_index_returns_200(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

    def test_index_lists_clients(self):
        resp = self.client.get("/")
        body = resp.data.decode()
        self.assertIn("TestClient_A", body)
        self.assertIn("TestClient_B", body)

    def test_index_shows_root_path(self):
        resp = self.client.get("/")
        body = resp.data.decode()
        self.assertIn(str(self.root), body)

    def test_index_has_client_links(self):
        resp = self.client.get("/")
        body = resp.data.decode()
        self.assertIn("/client/TestClient_A", body)

    def test_index_shows_document_counts(self):
        resp = self.client.get("/")
        body = resp.data.decode()
        # Each client has 2 docs; table should show the count
        self.assertIn("2", body)

    # --- client detail route ---

    def test_client_returns_200(self):
        resp = self.client.get("/client/TestClient_A")
        self.assertEqual(resp.status_code, 200)

    def test_client_shows_name(self):
        resp = self.client.get("/client/TestClient_A")
        body = resp.data.decode()
        self.assertIn("TestClient_A", body)

    def test_client_shows_tasks(self):
        resp = self.client.get("/client/TestClient_A")
        body = resp.data.decode()
        self.assertIn("Missing W-2 box 12", body)
        self.assertIn("Confirm mortgage payoff", body)

    def test_client_shows_workpaper_links(self):
        resp = self.client.get("/client/TestClient_A")
        body = resp.data.decode()
        self.assertIn("Return_Prep_Checklist.md", body)
        self.assertIn("Questions_For_Client.md", body)
        self.assertIn("Document_Index.csv", body)

    def test_client_back_link(self):
        resp = self.client.get("/client/TestClient_A")
        body = resp.data.decode()
        self.assertIn('href="/"', body)

    def test_client_not_found_returns_404(self):
        resp = self.client.get("/client/DoesNotExist")
        self.assertEqual(resp.status_code, 404)

    def test_client_file_instead_of_dir_returns_404(self):
        # Create a file (not a dir) at the client path
        stray = self.root / "not_a_dir"
        stray.write_text("oops")
        resp = self.client.get("/client/not_a_dir")
        self.assertEqual(resp.status_code, 404)

    # --- client with no workpapers ---

    def test_client_no_workpapers_shows_placeholder(self):
        empty = self.root / "EmptyClient"
        empty.mkdir()
        resp = self.client.get("/client/EmptyClient")
        self.assertEqual(resp.status_code, 200)
        body = resp.data.decode()
        self.assertIn("Generate workpapers first", body)


if __name__ == "__main__":
    unittest.main()
