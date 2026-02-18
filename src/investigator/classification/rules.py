"""Deterministic keyword-based incident classifier.

No LLM calls. Classification rules are explicit and auditable.
Adding or changing rules here is a code-reviewed, versioned change.
"""

import re
from dataclasses import dataclass

from investigator.models.classification import ClassificationResult, ClassificationType


@dataclass(frozen=True)
class _Rule:
    type: ClassificationType
    # Patterns matched against lowercased error_type OR error_message
    keywords: tuple[str, ...]
    # Confidence when matched via keyword (vs exact error_type match)
    keyword_confidence: float = 0.75
    exact_confidence: float = 0.92


# Rules evaluated in order; first match wins.
_RULES: tuple[_Rule, ...] = (
    _Rule(
        type=ClassificationType.schema_mismatch,
        keywords=(
            "schema_mismatch",
            "schema mismatch",
            "schema drift",
            "column missing",
            "column count changed",
            "missing column",
            "field missing",
            "incompatible schema",
        ),
    ),
    _Rule(
        type=ClassificationType.timeout,
        keywords=(
            "timeout",
            "timed out",
            "time out",
            "deadline exceeded",
            "exceeded maximum allowed runtime",
            "connection timed out",
            "read timed out",
            "query timed out",
        ),
    ),
    _Rule(
        type=ClassificationType.data_quality,
        keywords=(
            "data_quality",
            "data quality",
            "null value",
            "not-null constraint",
            "duplicate record",
            "referential integrity",
            "constraint violation",
            "out of range",
            "unexpected value",
        ),
    ),
    _Rule(
        type=ClassificationType.auth,
        keywords=(
            "^auth$",
            "unauthorized",
            "access denied",
            "forbidden",
            "401",
            "403",
            "permission denied",
            "token expired",
            "authentication failed",
            "credential",
        ),
    ),
    _Rule(
        type=ClassificationType.connectivity,
        keywords=(
            "connectivity",
            "connection refused",
            "cannot connect",
            "network unreachable",
            "no route to host",
            "connection reset",
            "broken pipe",
            "host unreachable",
        ),
    ),
)


def _matches(rule: _Rule, text: str) -> bool:
    for kw in rule.keywords:
        if re.search(re.escape(kw) if not kw.startswith("^") else kw, text, re.IGNORECASE):
            return True
    return False


class RulesClassifier:
    """Classify an incident using deterministic keyword rules.

    The classifier is intentionally simple and transparent — every decision
    can be traced to a keyword match in the rule table above.
    """

    def classify(self, *, error_type: str, error_message: str) -> ClassificationResult:
        combined = f"{error_type} {error_message}".lower()

        for rule in _RULES:
            # Exact error_type match → higher confidence
            if error_type.lower() == rule.type.value:
                return ClassificationResult(
                    type=rule.type,
                    confidence=rule.exact_confidence,
                    reason=f"Exact error_type match: {error_type!r}",
                )
            # Keyword match in combined text
            if _matches(rule, combined):
                matched = next(
                    kw for kw in rule.keywords
                    if re.search(re.escape(kw) if not kw.startswith("^") else kw, combined, re.IGNORECASE)
                )
                return ClassificationResult(
                    type=rule.type,
                    confidence=rule.keyword_confidence,
                    reason=f"Keyword match: {matched!r} in error_type/message",
                )

        return ClassificationResult(
            type=ClassificationType.unknown,
            confidence=0.1,
            reason=f"No rule matched error_type={error_type!r}",
        )
