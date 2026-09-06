"""Company negotiation policy: structured rules and per-rule check results.

No business logic here, just data - the PASS/BLOCKED/etc. comparisons
live in harness/policy_gate.py (see claude.md's schema-vs-harness rule).
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from .clause import ClauseValue


class ComparisonDirection(str, Enum):
    """How hard_limit_value bounds the vendor's value: MAX is a ceiling
    (lower is better, e.g. escalation), MIN is a floor (higher is
    better, e.g. SLA), EQUALS is an exact categorical match (e.g. data
    ownership).
    """

    MAX = "max"
    MIN = "min"
    EQUALS = "equals"


class PolicyRuleSource(str, Enum):
    """Where a PolicyRule's values came from - lets the harness tell a
    document-grounded value apart from an assumed one (agents/policy_analyst.py).
    """

    DEFAULT = "default"  # unmodified data/policy_config.json value, no extraction attempted
    EXTRACTED = "extracted"  # confidently pulled from an uploaded policy document
    DEFAULT_FALLBACK = "default_fallback"  # extraction attempted but fell back to the config default


class PolicyRule(BaseModel):
    """One company policy constraint for a single clause type."""

    clause_type: str
    target_value: ClauseValue = Field(
        description="Company's preferred value. Informative only - never enforced by the gate."
    )
    hard_limit_value: ClauseValue = Field(
        description=(
            "The enforced boundary. For rules with reference_clause_type "
            "set, this is a human-readable label for the boundary; its "
            "actual numeric value is resolved dynamically from another "
            "extracted clause at check time."
        )
    )
    direction: ComparisonDirection
    description: str = Field(description="Human-readable explanation of the rule.")
    expected_unit: Optional[str] = Field(
        default=None,
        description=(
            "Unit the vendor's value must be in, e.g. 'percent' or "
            "'days'. 'days' also tells the gate to parse duration text "
            "like 'Net 30' before comparing. None for categorical rules."
        ),
    )
    reference_clause_type: Optional[str] = Field(
        default=None,
        description=(
            "If set, hard_limit_value is resolved dynamically from the "
            "extracted Clause of this clause_type instead of being a fixed "
            "constant. Used by liability_cap, whose floor is the contract's "
            "own annual_contract_value, not a fixed number."
        ),
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="1.0 for hand-authored defaults; the extractor's own score when source=extracted.",
    )
    source: PolicyRuleSource = Field(
        default=PolicyRuleSource.DEFAULT,
        description="Where target_value/hard_limit_value came from - see PolicyRuleSource.",
    )


class PolicyConfig(BaseModel):
    """The full set of company negotiation policy rules."""

    version: str = "v1"
    rules: List[PolicyRule] = Field(default_factory=list)


class CheckStatus(str, Enum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    CANNOT_VERIFY = "CANNOT_VERIFY"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    CONFLICTING = "CONFLICTING"


class PolicyCheckResult(BaseModel):
    """Outcome of checking one PolicyRule against extracted evidence
    (and, once one exists, a proposed negotiation move).
    """

    clause_type: str
    status: CheckStatus
    checked_value: Optional[ClauseValue] = Field(
        default=None,
        description=(
            "The value the rule was actually evaluated against. For "
            "CONFLICTING this is the tie-broken value, not a literal "
            "extracted fact - see requires_human_signoff. None when the "
            "status is CANNOT_VERIFY or LOW_CONFIDENCE."
        ),
    )
    target_value: Optional[ClauseValue] = None
    hard_limit_value: Optional[ClauseValue] = None
    reason: str
    requires_human_signoff: bool = Field(
        default=False,
        description=(
            "True for CONFLICTING results: a tie-break was applied "
            "automatically for planning purposes, but a person must "
            "confirm it before the final recommendation is treated as final."
        ),
    )
    source_clauses: List[str] = Field(
        default_factory=list,
        description="clause_id values this result was derived from, for audit traceability.",
    )
