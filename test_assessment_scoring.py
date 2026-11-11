"""Unit tests for NeuroTrack AI assessment_scoring.py."""

import unittest
from datetime import date

from assessment_scoring import evaluate_assessment


class TestAssessmentScoring(unittest.TestCase):

    def setUp(self):
        self.assessment_date = date(2026, 11, 11)

        # Correct answers for every automatically scored question.
        # LAN001 is manually evaluated and supplied separately in tests.
        self.responses = {
            "Memory": {
                "MEM001": ["River", "Lemon", "Key"],
                "MEM002": "Lemon",
            },
            "Attention": {
                "ATT001": [5, 2, 8, 3],
                "ATT002": 3,
            },
            "Language": {
                "LAN001": ["apple", "banana", "mango", "orange", "grape"],
                "LAN002": "Fly",
            },
            "Orientation": {
                "ORI001": "November",
                "ORI002": 2026,
            },
            "Reasoning": {
                "REA001": 10,
                "REA002": "All roses are flowers",
            },
            "Visuospatial Skills": {
                "VIS001": "Square",
                "VIS002": "Square",
            },
        }

    def test_all_correct_answers_and_manual_score(self):
        result = evaluate_assessment(
            self.responses,
            assessment_date=self.assessment_date,
            manual_scores={"LAN001": 5},
        )

        self.assertEqual(result["scores"]["total_correct"], 21)
        self.assertEqual(result["scores"]["total_questions"], 21)
        self.assertEqual(result["scores"]["total_possible"], 21)
        self.assertEqual(result["scores"]["percentage"], 100.0)
        self.assertEqual(result["status"], "processed")
        self.assertEqual(result["pending_manual_review"], [])

    def test_manual_review_pending(self):
        result = evaluate_assessment(
            self.responses,
            assessment_date=self.assessment_date,
        )

        self.assertEqual(result["status"], "pending_manual_review")
        self.assertIn("LAN001", result["pending_manual_review"])
        self.assertEqual(
            result["scores"]["question_scores"]["LAN001"]["status"],
            "pending_manual",
        )

    def test_missing_answers(self):
        result = evaluate_assessment(
            {},
            assessment_date=self.assessment_date,
            manual_scores={"LAN001": 0},
        )

        self.assertEqual(result["scores"]["total_correct"], 0)
        self.assertEqual(result["scores"]["total_questions"], 21)
        self.assertEqual(
            result["scores"]["question_scores"]["MEM001"]["status"],
            "unanswered",
        )

    def test_invalid_answer_gets_zero(self):
        responses = {
            "Memory": {
                "MEM001": "not a word list",
                "MEM002": "Wrong answer",
            }
        }

        result = evaluate_assessment(
            responses,
            assessment_date=self.assessment_date,
            manual_scores={"LAN001": 0},
        )

        self.assertEqual(
            result["scores"]["question_scores"]["MEM001"]["status"],
            "invalid",
        )
        self.assertEqual(
            result["scores"]["question_scores"]["MEM002"]["score"],
            0,
        )

    def test_invalid_manual_score_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_assessment(
                self.responses,
                assessment_date=self.assessment_date,
                manual_scores={"LAN001": 10},
            )

    def test_partial_memory_and_sequence_scoring(self):
        responses = {
            "Memory": {
                "MEM001": ["River", "Key"],
            },
            "Attention": {
                "ATT001": [5, 0, 8, 3],
            },
        }

        result = evaluate_assessment(
            responses,
            assessment_date=self.assessment_date,
            manual_scores={"LAN001": 0},
        )

        self.assertEqual(
            result["scores"]["question_scores"]["MEM001"]["score"], 2
        )
        self.assertEqual(
            result["scores"]["question_scores"]["ATT001"]["score"], 3
        )

    def test_flat_question_id_response_format(self):
        responses = {
            "MEM001": ["River", "Lemon", "Key"],
            "MEM002": "Lemon",
            "ORI001": "Nov",
            "ORI002": "2026",
        }

        result = evaluate_assessment(
            responses,
            assessment_date=self.assessment_date,
            manual_scores={"LAN001": 0},
        )

        self.assertEqual(
            result["scores"]["question_scores"]["MEM001"]["score"], 3
        )
        self.assertEqual(
            result["scores"]["question_scores"]["ORI001"]["score"], 1
        )
        self.assertEqual(
            result["scores"]["question_scores"]["ORI002"]["score"], 1
        )

    def test_unknown_question_is_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_assessment(
                {"Memory": {"UNKNOWN": "answer"}},
                assessment_date=self.assessment_date,
                manual_scores={"LAN001": 0},
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
