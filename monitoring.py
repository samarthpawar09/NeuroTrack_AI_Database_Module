"""
NeuroTrack AI - cognitive assessment monitoring.

This module reads assessment history through the existing database.py API.
It does not generate diagnoses, dementia predictions, or clinical interpretations.
"""

from __future__ import annotations

from typing import Any

import database


def _scale_signature(item: dict[str, Any]) -> tuple:
    """Describe the scoring scale so unlike assessments are not compared."""
    domain_scores = item.get("domain_scores") or {}
    domain_maxima = tuple(
        sorted(
            (str(domain), _domain_maximum(values))
            for domain, values in domain_scores.items()
        )
    )
    return (
        item.get("assessment_version"),
        item.get("total_questions"),
        domain_maxima,
    )


def _domain_maximum(values: Any) -> Any:
    if isinstance(values, dict):
        return values.get("maximum_score")
    return None


def _domain_score_value(values: Any) -> Any:
    """Return the earned/raw score from the stored domain-score structure."""
    if isinstance(values, dict):
        return values.get("score")
    return values


def get_assessment_history(
    user_id: int,
    db_path: str | None = None,
) -> dict[str, Any]:
    """
    Return a user's assessments in chronological order.

    An assessment is comparable to the immediately preceding assessment only
    when both have the same assessment_version and the same overall and
    domain maximum-score scales.
    """
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer.")

    # database.get_user_assessments returns newest first; reverse it.
    records = database.get_user_assessments(user_id, db_path=db_path)
    records.reverse()

    history: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None

    for record in records:
        domains = record.get("domain_scores") or {}
        current_signature = _scale_signature(record)
        comparable = (
            previous is not None
            and current_signature == _scale_signature(previous)
            and record.get("assessment_version") is not None
        )

        entry: dict[str, Any] = {
            "assessment_id": record["assessment_id"],
            "date": record["assessment_date"],
            "assessment_version": record.get("assessment_version"),
            "overall_score": record["percentage"],
            "raw_score": record["total_correct"],
            "maximum_score": record["total_questions"],
            "domain_scores": domains,
            "status": record.get("status"),
            "comparable_to_previous": comparable,
        }

        # Convenience fields requested for monitoring views, e.g. memory_score.
        for domain, values in domains.items():
            key = str(domain).strip().lower().replace(" ", "_") + "_score"
            entry[key] = _domain_score_value(values)

        history.append(entry)
        previous = record

    return {
        "user_id": user_id,
        "assessment_count": len(history),
        "assessment_history": history,
    }


# A short alias for callers that prefer the assignment's monitoring terminology.
get_user_monitoring_history = get_assessment_history
