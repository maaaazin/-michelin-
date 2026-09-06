"""Deterministic evidence-grounding check - no LLM calls. Verifies a
NegotiationProposal's cited clause_ids actually exist in the extracted
evidence, and that numeric claims in its rationale don't contradict the
vendor_value of a clause it cites. This is "don't invent facts"
enforced in code, not just requested in a prompt.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from schemas import CheckStatus, Clause, NegotiationProposal, PolicyCheckResult

# Matches comma-grouped numbers ("1,000,000") as one token before falling
# back to plain digits - otherwise a comma splits a large figure into
# fragments ("1", "000", "000") that never equal the clause's real value,
# producing a false grounding failure on any rationale that writes a large
# number the ordinary way.
_NUMBER_PATTERN = re.compile(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?")


class GroundingStatus(str, Enum):
    PASSED = "PASSED"
    GROUNDING_FAILED = "GROUNDING_FAILED"


class GroundingCheckResult(BaseModel):
    """Outcome of checking one NegotiationProposal's evidence grounding."""

    status: GroundingStatus
    reason: str
    missing_clause_ids: List[str] = Field(default_factory=list)
    contradicted_clause_ids: List[str] = Field(default_factory=list)


def check_grounding(
    proposal: NegotiationProposal,
    clauses: List[Clause],
    policy_results: Optional[List[PolicyCheckResult]] = None,
) -> GroundingCheckResult:
    """Check that every clause_id in supporting_clauses exists, and that
    numbers in the rationale don't contradict a cited clause's own
    vendor_value (a substring/number heuristic, not exact parsing).

    policy_results is optional, for backward compatibility; when given,
    a CONFLICTING clause_type is also exempt from the number check - its
    rationale mentions are the harness's own tie-broken value (ADR-007),
    not a claim about what the clause itself literally states.
    """
    by_id = {c.clause_id: c for c in clauses if c.clause_id}

    missing = [cid for cid in proposal.supporting_clauses if cid not in by_id]
    if missing:
        return GroundingCheckResult(
            status=GroundingStatus.GROUNDING_FAILED,
            reason=f"Proposal cites unknown clause_id(s): {missing}",
            missing_clause_ids=missing,
        )

    # A clause being proposed for change (a concessions/requested_changes
    # key) is expected to discuss the new value, not restate the old one -
    # only check number consistency for clauses cited as unchanging fact.
    changing_types = set(proposal.concessions) | set(proposal.requested_changes)
    if policy_results:
        changing_types |= {r.clause_type for r in policy_results if r.status == CheckStatus.CONFLICTING}
    rationale_numbers = {float(n.replace(",", "")) for n in _NUMBER_PATTERN.findall(proposal.rationale)}
    contradicted: List[str] = []
    if rationale_numbers:
        for cid in proposal.supporting_clauses:
            clause = by_id[cid]
            if clause.clause_type in changing_types:
                continue
            value = clause.vendor_value
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if float(value) not in rationale_numbers:
                    contradicted.append(cid)

    if contradicted:
        return GroundingCheckResult(
            status=GroundingStatus.GROUNDING_FAILED,
            reason=f"Rationale's numbers don't match the cited clause value(s) for: {contradicted}",
            contradicted_clause_ids=contradicted,
        )

    return GroundingCheckResult(
        status=GroundingStatus.PASSED,
        reason="All cited clauses exist and are numerically consistent.",
    )
