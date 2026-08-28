import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from config import Settings
from database import get_db
from main import app, get_rag_service, get_storage_service


class BackendApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

        self.mock_db = MagicMock()
        self.mock_rag = MagicMock()
        self.mock_storage = MagicMock()

        app.dependency_overrides[get_db] = lambda: self.mock_db
        app.dependency_overrides[get_rag_service] = lambda: self.mock_rag
        app.dependency_overrides[get_storage_service] = lambda: self.mock_storage

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_health_check(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_upload_invalid_extension(self):
        response = self.client.post(
            "/upload",
            files={"file": ("malicious.exe", b"binary content", "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported file type", response.json()["detail"])

    def test_upload_success(self):
        self.mock_storage.upload_fileobj.return_value = None

        response = self.client.post(
            "/upload",
            files={"file": ("sample.txt", b"hello world context", "text/plain")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["original_name"], "sample.txt")
        self.assertIn("filename", data)
        self.mock_storage.upload_fileobj.assert_called_once()
        self.mock_db.add.assert_called_once()
        self.mock_db.commit.assert_called_once()

    def test_chat_endpoint_success(self):
        self.mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        self.mock_rag.rewrite_query = AsyncMock(return_value="What is Mars?")
        self.mock_rag.retrieve_contexts = AsyncMock(
            return_value=(["Mars is the fourth planet."], "Mars is the fourth planet.")
        )
        self.mock_rag.format_prompt.return_value = "Formatted Prompt"
        self.mock_rag.generate_answer = AsyncMock(return_value="Mars is the 4th planet.")

        response = self.client.post(
            "/chat",
            json={"question": "What is the fourth planet?", "session_id": "test_sess"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["answer"], "Mars is the 4th planet.")
        self.assertIn("Mars", data["context_used"])

    def test_chat_stream_endpoint(self):
        self.mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        self.mock_rag.rewrite_query = AsyncMock(return_value="Tell me about Jupiter.")
        self.mock_rag.retrieve_contexts = AsyncMock(
            return_value=(["Jupiter is large."], "Jupiter is large.")
        )
        self.mock_rag.format_prompt.return_value = "Prompt text"

        async def _mock_stream(_prompt):
            for token in ["Jupiter ", "is ", "the ", "largest."]:
                yield token

        self.mock_rag.stream_answer = _mock_stream

        with patch("main.SessionLocal") as mock_session_local:
            mock_session = MagicMock()
            mock_session_local.return_value.__enter__.return_value = mock_session

            with self.client.stream(
                "POST",
                "/chat/stream",
                json={"question": "Tell me about Jupiter", "session_id": "stream_sess"},
            ) as response:
                self.assertEqual(response.status_code, 200)
                lines = [line for line in response.iter_lines() if line.strip()]
                self.assertTrue(len(lines) >= 2)
                self.assertTrue(lines[0].startswith("data:"))

    def test_analytics_stats(self):
        self.mock_db.query.return_value.count.return_value = 5
        self.mock_db.query.return_value.filter.return_value.count.return_value = 3
        self.mock_db.query.return_value.distinct.return_value.count.return_value = 2
        self.mock_db.query.return_value.filter.return_value.scalar.return_value = 1.25

        response = self.client.get("/analytics/stats")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_documents", data)
        self.assertIn("embedded_documents", data)
        self.assertIn("active_sessions", data)
        self.assertIn("avg_latency_seconds", data)

    def test_analytics_vectors_empty(self):
        self.mock_rag.qdrant_client.scroll.return_value = ([], None)

        response = self.client.get("/analytics/vectors")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"points": []})


if __name__ == "__main__":
    unittest.main()
