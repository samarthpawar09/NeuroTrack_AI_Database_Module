"""Basic automated tests for NeuroTrack AI database.py; uses a temporary DB."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

import database # type: ignore


class DatabaseTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Path(self.temp_dir.name) / "test_neurotrack.db"

        database.init_db(self.db)

        self.user_id = database.create_user(
            "Test User",
            "test@example.com",
            "SecurePass123",
            self.db
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def sample_assessment(self):
        return {
            "assessment_id": str(uuid4()),
            "assessment_version": "demo-v3",
            "assessment_date": "2026-11-03T00:00:00Z",
            "responses": {
                "attention": {
                    "Q02": "7"
                }
            },
            "scores": {
                "total_correct": 1,
                "total_questions": 1,
                "percentage": 100.0,
                "domain_scores": {
                    "attention": {
                        "correct": 1,
                        "total": 1
                    }
                }
            },
            "prediction": None,
            "status": "processed_not_saved"
        }

    def test_create_and_get_user(self):
        user = database.get_user_by_email(
            "TEST@example.com", self.db
        )

        self.assertEqual(user["user_id"], self.user_id)

        self.assertTrue(
            database.verify_password(
                "SecurePass123",
                user["password_hash"]
            )
        )

        self.assertFalse(
            database.verify_password(
                "wrong-password",
                user["password_hash"]
            )
        )

    def test_duplicate_email_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            database.create_user(
                "Other",
                "test@example.com",
                "SecurePass123",
                self.db
            )

    def test_save_and_retrieve_assessment(self):
        assessment = self.sample_assessment()

        saved_id = database.save_assessment(
            self.user_id, assessment, self.db
        )

        self.assertEqual(
            saved_id,
            assessment["assessment_id"]
        )

        result = database.get_assessment_by_id(
            saved_id, self.user_id, self.db
        )

        self.assertEqual(
            result["responses"]["attention"]["Q02"],
            "7"
        )

        self.assertEqual(result["percentage"], 100.0)

    def test_history_is_user_scoped(self):
        assessment = self.sample_assessment()

        database.save_assessment(
            self.user_id, assessment, self.db
        )

        history = database.get_user_assessments(
            self.user_id, self.db
        )

        self.assertEqual(len(history), 1)

        other_user = database.create_user(
            "Other User",
            "other@example.com",
            "AnotherPass123",
            self.db
        )

        self.assertEqual(
            database.get_user_assessments(other_user, self.db),
            []
        )

        self.assertIsNone(
            database.get_assessment_by_id(
                assessment["assessment_id"],
                other_user,
                self.db
            )
        )

    def test_foreign_key_and_atomic_rollback(self):

        # Test foreign-key constraint
        with self.assertRaises(sqlite3.IntegrityError):
            database.save_assessment(
                999999,
                self.sample_assessment(),
                self.db
            )

        assessment = self.sample_assessment()
        assessment_id = assessment["assessment_id"]

        # Create trigger and explicitly close connection
        conn = sqlite3.connect(self.db)

        try:
            conn.execute("""
                CREATE TRIGGER reject_test_response
                BEFORE INSERT ON assessment_responses
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'forced response failure'
                    );
                END
            """)

            conn.commit()

        finally:
            conn.close()

        # Test transaction rollback
        with self.assertRaises(sqlite3.IntegrityError):
            database.save_assessment(
                self.user_id,
                assessment,
                self.db
            )

        # Check that incomplete assessment was not saved
        conn = sqlite3.connect(self.db)

        try:
            count = conn.execute(
                """
                SELECT COUNT(*)
                FROM assessments
                WHERE assessment_id = ?
                """,
                (assessment_id,)
            ).fetchone()[0]

        finally:
            conn.close()

        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
