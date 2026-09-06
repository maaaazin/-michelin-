"""Deterministic policy engine - pure Python, no LLM calls (claude.md).
One function serves both POLICY_CHECK (proposal=None) and POLICY_GATE
(proposal set) from architecture.md Section 5.2. Status priority per
rule: CANNOT_VERIFY > CONFLICTING > LOW_CONFIDENCE > PASS/BLOCKED;
rationale for that ordering and the edge cases is in decisions.md
ADR-006/007.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

from schemas import (
    CheckStatus,
    Clause,
    ClauseValue,
    ComparisonDirection,
    NegotiationProposal,
    PolicyCheckResult,
    PolicyConfig,
    PolicyRule,
)

# ADR-006: evidence below this confidence score is never treated as fact.
CONFIDENCE_THRESHOLD = 0.6

DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / "data" / "policy_config.json"


def load_policy_config(path: Union[str, Path] = DEFAULT_POLICY_PATH) -> PolicyConfig:
    """Load the company policy from a JSON fixture into a PolicyConfig."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return PolicyConfig.model_validate(raw)


@dataclass
class _ClauseGroupResult:
    """Outcome of resolving all evidence for one clause_type. If
    blocking_status is None, value holds a usable value; otherwise this
    result is itself the final status - no hard-limit check follows.
    """

    blocking_status: Optional[CheckStatus]
    value: Optional[ClauseValue]
    reason: Optional[str]
    source_clause_ids: List[str] = field(default_factory=list)
    requires_human_signoff: bool = False
    conflicting_clauses: List[Clause] = field(default_factory=list)


def _evaluate_clause_group(clause_type: str, clauses: List[Clause]) -> _ClauseGroupResult:
    """Resolve every extracted Clause matching one clause_type into either
    a single usable value or a reason it cannot be used.
    """
    matches = [c for c in clauses if c.clause_type == clause_type]
    specified = [c for c in matches if not c.not_specified]

    # Edge case (a): the vendor contract never addresses this clause type
    # at all, or every matching entry is an explicit NOT_SPECIFIED marker.
    if not specified:
        return _ClauseGroupResult(
            blocking_status=CheckStatus.CANNOT_VERIFY,
            value=None,
            reason=(
                f"Vendor contract does not address '{clause_type}' "
                "(NOT_SPECIFIED) - cannot verify, not a pass or a fail."
            ),
            source_clause_ids=[c.clause_id for c in matches if c.clause_id],
        )

    # Edge case (c): more than one specified clause disagrees on the value.
    distinct_values = {c.vendor_value for c in specified}
    if len(distinct_values) > 1:
        return _ClauseGroupResult(
            blocking_status=CheckStatus.CONFLICTING,
            value=None,
            reason=None,  # filled in by the caller once the rule's direction is known
            source_clause_ids=[c.clause_id for c in specified if c.clause_id],
            requires_human_signoff=True,
            conflicting_clauses=specified,
        )

    # Edge case (b): a single piece of evidence, but not trustworthy enough.
    clause = specified[0]
    if clause.confidence < CONFIDENCE_THRESHOLD:
        return _ClauseGroupResult(
            blocking_status=CheckStatus.LOW_CONFIDENCE,
            value=None,
            reason=(
                f"Evidence for '{clause_type}' has confidence "
                f"{clause.confidence:.2f}, below the {CONFIDENCE_THRESHOLD} "
                "threshold - blocked from use as fact, flagged for review."
            ),
            source_clause_ids=[clause.clause_id] if clause.clause_id else [],
        )

    return _ClauseGroupResult(
        blocking_status=None,
        value=clause.vendor_value,
        reason=None,
        source_clause_ids=[clause.clause_id] if clause.clause_id else [],
    )


def _tie_break(direction: ComparisonDirection, values: List[ClauseValue]) -> Optional[ClauseValue]:
    """Contradiction tie-break (ADR-007): pick whichever conflicting
    value scores better under the rule's own direction - min for MAX
    (lower is better), max for MIN (higher is better). EQUALS or a
    non-numeric conflict is left unresolved for human review.
    """
    numeric_values = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if len(numeric_values) != len(values):
        return None
    if direction == ComparisonDirection.MAX:
        return min(numeric_values)
    if direction == ComparisonDirection.MIN:
        return max(numeric_values)
    return None


def _compare(direction: ComparisonDirection, value: ClauseValue, limit: ClauseValue) -> bool:
    """The actual hard-limit comparison. Plain code, no LLM in sight."""
    if direction == ComparisonDirection.EQUALS:
        return str(value).strip().lower() == str(limit).strip().lower()
    try:
        numeric_value = float(value)
        numeric_limit = float(limit)
    except (TypeError, ValueError):
        return False
    if direction == ComparisonDirection.MAX:
        return numeric_value <= numeric_limit
    if direction == ComparisonDirection.MIN:
        return numeric_value >= numeric_limit
    return False


def _describe_comparison(rule: PolicyRule, value: ClauseValue, limit: ClauseValue, passed: bool) -> str:
    status_word = "PASS" if passed else "BLOCKED"
    if rule.direction == ComparisonDirection.MAX:
        limit_desc = f"hard maximum {limit}"
        verb = "within" if passed else "exceeds"
    elif rule.direction == ComparisonDirection.MIN:
        limit_desc = f"hard minimum {limit}"
        verb = "meets" if passed else "falls short of"
    else:
        limit_desc = f"required value {limit!r}"
        verb = "matches" if passed else "does not match"
    return f"{status_word}: '{rule.clause_type}' value {value!r} {verb} {limit_desc}."


def evaluate_rule(
    rule: PolicyRule,
    clauses: List[Clause],
    proposal: Optional[NegotiationProposal] = None,
) -> PolicyCheckResult:
    """Check a single PolicyRule against the extracted evidence (and,
    if given, a proposed negotiation move). Returns exactly one
    PolicyCheckResult - see the module docstring for the priority order
    among the possible statuses.
    """
    group = _evaluate_clause_group(rule.clause_type, clauses)

    # Edge case (c), continued: a contradiction was found - tie-break and
    # surface it, rather than silently picking one clause and moving on.
    if group.blocking_status == CheckStatus.CONFLICTING:
        values = [c.vendor_value for c in group.conflicting_clauses]
        sections = [c.source_section or "unspecified section" for c in group.conflicting_clauses]
        resolved = _tie_break(rule.direction, values)
        pairs = "; ".join(f"{s}: {v!r}" for s, v in zip(sections, values))
        reason = (
            f"Conflicting evidence for '{rule.clause_type}' ({pairs}). "
            f"Defaulting to {resolved!r} (the more conservative, "
            "company-favorable value) for negotiation planning; flagged "
            "for human sign-off before this is treated as final."
        )
        return PolicyCheckResult(
            clause_type=rule.clause_type,
            status=CheckStatus.CONFLICTING,
            checked_value=resolved,
            target_value=rule.target_value,
            hard_limit_value=rule.hard_limit_value,
            reason=reason,
            requires_human_signoff=True,
            source_clauses=group.source_clause_ids,
        )

    # Edge cases (a) and (b): no usable evidence at all, or evidence that
    # exists but is not trustworthy enough. Either way, stop here - do
    # not attempt a PASS/BLOCKED determination on unusable evidence.
    if group.blocking_status is not None:
        return PolicyCheckResult(
            clause_type=rule.clause_type,
            status=group.blocking_status,
            checked_value=None,
            target_value=rule.target_value,
            hard_limit_value=rule.hard_limit_value,
            reason=group.reason or "",
            requires_human_signoff=False,
            source_clauses=group.source_clause_ids,
        )

    # Evidence is usable. Resolve the hard limit, which may itself be
    # dynamic (liability_cap's floor is another extracted clause, not a
    # fixed constant).
    hard_limit: ClauseValue = rule.hard_limit_value
    extra_source_ids: List[str] = []
    if rule.reference_clause_type:
        ref_group = _evaluate_clause_group(rule.reference_clause_type, clauses)

        if ref_group.blocking_status == CheckStatus.CONFLICTING:
            values = [c.vendor_value for c in ref_group.conflicting_clauses]
            resolved = _tie_break(rule.direction, values)
            return PolicyCheckResult(
                clause_type=rule.clause_type,
                status=CheckStatus.CONFLICTING,
                checked_value=group.value,
                target_value=rule.target_value,
                hard_limit_value=rule.hard_limit_value,
                reason=(
                    f"Cannot resolve the hard limit for '{rule.clause_type}': "
                    f"the referenced value '{rule.reference_clause_type}' is "
                    f"itself conflicting across clauses ({values}). "
                    f"Defaulting to {resolved!r} for planning; flagged for "
                    "human sign-off."
                ),
                requires_human_signoff=True,
                source_clauses=group.source_clause_ids + ref_group.source_clause_ids,
            )

        if ref_group.blocking_status is not None:
            return PolicyCheckResult(
                clause_type=rule.clause_type,
                status=ref_group.blocking_status,
                checked_value=None,
                target_value=rule.target_value,
                hard_limit_value=rule.hard_limit_value,
                reason=(
                    f"Cannot evaluate '{rule.clause_type}' against "
                    f"'{rule.reference_clause_type}': {ref_group.reason}"
                ),
                requires_human_signoff=False,
                source_clauses=group.source_clause_ids + ref_group.source_clause_ids,
            )

        hard_limit = ref_group.value  # type: ignore[assignment]
        extra_source_ids = ref_group.source_clause_ids

    # A proposed move, if given, overrides the raw vendor value here -
    # this is what makes one function serve both POLICY_CHECK and
    # POLICY_GATE (module docstring).
    value_to_check = group.value
    if proposal is not None:
        if rule.clause_type in proposal.concessions:
            value_to_check = proposal.concessions[rule.clause_type]
        elif rule.clause_type in proposal.requested_changes:
            value_to_check = proposal.requested_changes[rule.clause_type]

    passed = _compare(rule.direction, value_to_check, hard_limit)
    status = CheckStatus.PASS if passed else CheckStatus.BLOCKED
    reason = _describe_comparison(rule, value_to_check, hard_limit, passed)

    return PolicyCheckResult(
        clause_type=rule.clause_type,
        status=status,
        checked_value=value_to_check,
        target_value=rule.target_value,
        hard_limit_value=hard_limit,
        reason=reason,
        requires_human_signoff=False,
        source_clauses=group.source_clause_ids + extra_source_ids,
    )


def run_policy_check(
    clauses: List[Clause],
    policy: PolicyConfig,
    proposal: Optional[NegotiationProposal] = None,
) -> List[PolicyCheckResult]:
    """Run every rule in the policy against the extracted evidence (and,
    if given, a proposed move). This is the one function the graph calls
    at both the POLICY_CHECK and POLICY_GATE stages.
    """
    return [evaluate_rule(rule, clauses, proposal) for rule in policy.rules]
