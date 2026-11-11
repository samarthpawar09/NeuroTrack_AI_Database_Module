"""Unit tests for NeuroTrack AI monitoring history."""

import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

import database
from monitoring import get_assessment_history


class MonitoringTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_neurotrack.db")
        database.init_db(self.db_path)
        self.user_id = database.create_user(
            "Test User", "monitoring@example.com", "TestPass123", self.db_path
        )
        self.other_user_id = database.create_user(
            "Other User", "other@example.com", "TestPass123", self.db_path
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def save_assessment(self, user_id, date, version="1.0", total=8,
                        memory_score=2, memory_max=3):
        domain_scores = {
            "Memory": {
                "score": memory_score,
                "maximum_score": memory_max,
                "percentage": (memory_score / memory_max * 100) if memory_max else 0,
                "pending_manual": 0,
            },
            "Attention": {
                "score": 3,
                "maximum_score": 5,
                "percentage": 60,
                "pending_manual": 0,
            },
        }
        return database.save_assessment(
            user_id,
            {
                "assessment_id": str(uuid4()),
                "assessment_version": version,
                "assessment_date": date,
                "scores": {
                    "total_correct": total,
                    "total_questions": 10,
                    "percentage": total * 10,
                    "domain_scores": domain_scores,
                },
                "responses": {"Memory": {"MEM001": ["apple"]}},
                "status": "processed",
            },
            self.db_path,
        )

    def test_empty_history(self):
        result = get_assessment_history(self.user_id, self.db_path)
        self.assertEqual(result["assessment_count"], 0)
        self.assertEqual(result["assessment_history"], [])

    def test_history_is_chronological(self):
        self.save_assessment(self.user_id, "2026-11-03T09:00:00Z")
        self.save_assessment(self.user_id, "2026-11-01T09:00:00Z")
        result = get_assessment_history(self.user_id, self.db_path)
        dates = [x["date"] for x in result["assessment_history"]]
        self.assertEqual(dates, ["2026-11-01T09:00:00Z", "2026-11-03T09:00:00Z"])

    def test_only_requested_users_history_is_returned(self):
        self.save_assessment(self.user_id, "2026-11-01T09:00:00Z")
        self.save_assessment(self.other_user_id, "2026-11-02T09:00:00Z")
        result = get_assessment_history(self.user_id, self.db_path)
        self.assertEqual(result["assessment_count"], 1)
        self.assertEqual(result["user_id"], self.user_id)

    def test_same_version_and_scale_are_comparable(self):
        self.save_assessment(self.user_id, "2026-11-01T09:00:00Z")
        self.save_assessment(self.user_id, "2026-11-02T09:00:00Z")
        history = get_assessment_history(self.user_id, self.db_path)["assessment_history"]
        self.assertFalse(history[0]["comparable_to_previous"])
        self.assertTrue(history[1]["comparable_to_previous"])

    def test_different_version_is_not_comparable(self):
        self.save_assessment(self.user_id, "2026-11-01T09:00:00Z", version="1.0")
        self.save_assessment(self.user_id, "2026-11-02T09:00:00Z", version="2.0")
        history = get_assessment_history(self.user_id, self.db_path)["assessment_history"]
        self.assertFalse(history[1]["comparable_to_previous"])

    def test_domain_score_convenience_field(self):
        self.save_assessment(self.user_id, "2026-11-01T09:00:00Z", memory_score=2)
        item = get_assessment_history(self.user_id, self.db_path)["assessment_history"][0]
        self.assertEqual(item["memory_score"], 2)
        self.assertEqual(item["attention_score"], 3)

    def test_invalid_user_id(self):
        with self.assertRaises(ValueError):
            get_assessment_history(0, self.db_path)


if __name__ == "__main__":
    unittest.main()
