"""
NeuroTrack AI - Cognitive Assessment Scoring
Educational/research screening support only; not a clinically validated diagnostic tool.
"""

import json
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4


BASE_DIR = Path(__file__).resolve().parent
QUESTION_BANK_PATH = BASE_DIR / "questions" / "question_bank.json"


def load_question_bank(path=QUESTION_BANK_PATH):
    """Load and validate the question bank JSON."""
    with open(path, "r", encoding="utf-8") as file:
        bank = json.load(file)

    if not isinstance(bank, dict):
        raise ValueError("Question bank must be a JSON object.")

    if not isinstance(bank.get("domains"), list):
        raise ValueError("Question bank must contain a domains list.")

    if not isinstance(bank.get("questions"), list):
        raise ValueError("Question bank must contain a questions list.")

    seen_ids = set()
    for question in bank["questions"]:
        required = {
            "question_id", "domain", "answer_type",
            "maximum_score", "scoring_mode"
        }
        missing = required - set(question)
        if missing:
            raise ValueError(
                f"Question is missing required fields: {sorted(missing)}"
            )

        qid = question["question_id"]
        if qid in seen_ids:
            raise ValueError(f"Duplicate question ID: {qid}")
        seen_ids.add(qid)

        if question["domain"] not in bank["domains"]:
            raise ValueError(f"Unknown domain for {qid}: {question['domain']}")

        maximum = question["maximum_score"]
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 0:
            raise ValueError(f"Invalid maximum_score for {qid}")

        if question["scoring_mode"] not in ("automatic", "manual"):
            raise ValueError(f"Invalid scoring_mode for {qid}")

    return bank


def _normalize(value):
    if isinstance(value, str):
        return value.strip().casefold()
    return value


def _coerce_assessment_datetime(value):
    """Return an aware datetime in UTC. Accept date, datetime, or ISO string."""
    if value is None:
        return datetime.now(timezone.utc)

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("assessment_date must be a valid ISO date/time.") from exc
    else:
        raise TypeError("assessment_date must be a date, datetime, ISO string, or None.")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def score_question(question, answer, assessment_date=None):
    """
    Score one question.
    Returns (score, status), where status is automatic, unanswered,
    invalid, or pending_manual.
    """
    maximum = question["maximum_score"]

    if answer is None or answer == "":
        return 0, "unanswered"

    if question["scoring_mode"] == "manual":
        return 0, "pending_manual"

    answer_type = question["answer_type"]
    correct = question.get("correct_answer")
    qid = question["question_id"]

    # Orientation questions are checked against the assessment date.
    if qid in ("ORI001", "ORI002"):
        if assessment_date is None:
            return 0, "invalid"

        if qid == "ORI001":
            accepted_months = {
                assessment_date.strftime("%B").casefold(),
                assessment_date.strftime("%b").casefold(),
            }
            is_correct = (
                isinstance(answer, str)
                and answer.strip().casefold() in accepted_months
            )
        else:
            try:
                if isinstance(answer, bool):
                    return 0, "invalid"
                is_correct = int(answer) == assessment_date.year
            except (TypeError, ValueError):
                return 0, "invalid"

        return (maximum if is_correct else 0), "automatic"

    if answer_type == "mcq":
        if not isinstance(answer, str):
            return 0, "invalid"
        is_correct = _normalize(answer) == _normalize(correct)
        return (maximum if is_correct else 0), "automatic"

    if answer_type == "text":
        if not isinstance(answer, str):
            return 0, "invalid"
        is_correct = _normalize(answer) == _normalize(correct)
        return (maximum if is_correct else 0), "automatic"

    if answer_type == "word_list":
        if not isinstance(answer, (list, tuple)):
            return 0, "invalid"
        expected = {_normalize(word) for word in (correct or [])}
        submitted = {
            _normalize(word) for word in answer if isinstance(word, str)
        }
        points = len(expected.intersection(submitted))
        return min(points, maximum), "automatic"

    if answer_type == "numeric_sequence":
        if not isinstance(answer, (list, tuple)):
            return 0, "invalid"
        points = 0
        for submitted, expected in zip(answer, correct or []):
            if isinstance(submitted, bool):
                continue
            try:
                if int(submitted) == expected and str(submitted).strip() != "":
                    points += 1
            except (TypeError, ValueError):
                continue
        return min(points, maximum), "automatic"

    if answer_type == "number":
        if isinstance(answer, bool):
            return 0, "invalid"
        try:
            is_correct = int(answer) == int(correct)
        except (TypeError, ValueError):
            return 0, "invalid"
        return (maximum if is_correct else 0), "automatic"

    # Unsupported answer types are explicitly marked invalid.
    return 0, "invalid"


def _flatten_responses(responses, bank):
    """
    Accept either:
      {"Memory": {"MEM001": [...]}, ...}
    or:
      {"MEM001": [...], "MEM002": "..."}
    """
    question_map = {q["question_id"]: q for q in bank["questions"]}
    flattened = {}

    for key, value in responses.items():
        if key in bank["domains"]:
            if not isinstance(value, dict):
                raise TypeError(f"Responses for domain '{key}' must be a dictionary.")
            for qid, answer in value.items():
                if qid not in question_map:
                    raise ValueError(f"Unknown question ID: {qid}")
                if question_map[qid]["domain"] != key:
                    raise ValueError(f"{qid} does not belong to domain '{key}'.")
                if qid in flattened:
                    raise ValueError(f"Duplicate response for question {qid}.")
                flattened[qid] = answer
        elif key in question_map:
            if key in flattened:
                raise ValueError(f"Duplicate response for question {key}.")
            flattened[key] = value
        else:
            raise ValueError(f"Unknown response key or domain: {key}")

    return flattened


def evaluate_assessment(
    responses,
    assessment_date=None,
    manual_scores=None,
    question_bank_path=QUESTION_BANK_PATH,
):
    """
    Evaluate a complete or partial assessment.

    Manual scores are supplied as:
        {"LAN001": 4}

    Responses can be grouped by domain or keyed directly by question ID.
    """
    if not isinstance(responses, dict):
        raise TypeError("responses must be a dictionary.")

    if manual_scores is None:
        manual_scores = {}
    if not isinstance(manual_scores, dict):
        raise TypeError("manual_scores must be a dictionary.")

    bank = load_question_bank(question_bank_path)
    assessment_dt = _coerce_assessment_datetime(assessment_date)
    flattened = _flatten_responses(responses, bank)

    question_map = {q["question_id"]: q for q in bank["questions"]}

    for qid, score in manual_scores.items():
        question = question_map.get(qid)
        if question is None or question["scoring_mode"] != "manual":
            raise ValueError(f"Invalid manual scoring question: {qid}")

        maximum = question["maximum_score"]
        if (
            isinstance(score, bool)
            or not isinstance(score, int)
            or not 0 <= score <= maximum
        ):
            raise ValueError(f"Invalid manual score for {qid}; expected 0 to {maximum}.")

    domain_scores = {}
    question_scores = {}
    pending_manual_questions = []
    total_score = 0
    total_maximum = 0

    for domain in bank["domains"]:
        domain_earned = 0
        domain_maximum = 0
        domain_pending = 0

        for question in bank["questions"]:
            if question["domain"] != domain:
                continue

            qid = question["question_id"]
            maximum = question["maximum_score"]
            answer = flattened.get(qid)

            if question["scoring_mode"] == "manual":
                if qid in manual_scores:
                    score = manual_scores[qid]
                    status = "manual_reviewed"
                else:
                    score = 0
                    status = "pending_manual"
                    domain_pending += 1
                    pending_manual_questions.append(qid)
            else:
                score, status = score_question(
                    question, answer, assessment_dt
                )

            domain_earned += score
            domain_maximum += maximum

            question_scores[qid] = {
                "domain": domain,
                "score": score,
                "maximum_score": maximum,
                "status": status,
            }

        domain_scores[domain] = {
            "score": domain_earned,
            "maximum_score": domain_maximum,
            "percentage": round(domain_earned / domain_maximum * 100, 2)
            if domain_maximum else 0.0,
            "pending_manual": domain_pending,
        }

        total_score += domain_earned
        total_maximum += domain_maximum

    percentage = round(total_score / total_maximum * 100, 2) if total_maximum else 0.0
    overall_status = "pending_manual_review" if pending_manual_questions else "processed"

    scores = {
        "total_correct": total_score,
        "total_questions": total_maximum,
        "total_possible": total_maximum,  # Compatibility alias for earlier tests.
        "percentage": percentage,
        "domain_scores": domain_scores,
        "question_scores": question_scores,
    }

    return {
        "assessment_id": str(uuid4()),
        "assessment_version": bank.get("version", "1.0"),
        "assessment_date": assessment_dt.isoformat().replace("+00:00", "Z"),
        "scores": scores,
        "responses": responses,
        "status": overall_status,
        "pending_manual_review": pending_manual_questions,
    }
