"""Deterministic evidence-grounding check - no LLM calls. Verifies a
NegotiationProposal's cited clause_ids actually exist in the extracted
evidence, and that numeric claims in its rationale don't contradict the
vendor_value of a clause it cites. This is "don't invent facts"
enforced in code, not just requested in a prompt.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import List

from pydantic import BaseModel, Field

from schemas import Clause, NegotiationProposal


class GroundingStatus(str, Enum):
    PASSED = "PASSED"
    GROUNDING_FAILED = "GROUNDING_FAILED"


class GroundingCheckResult(BaseModel):
    """Outcome of checking one NegotiationProposal's evidence grounding."""

    status: GroundingStatus
    reason: str
    missing_clause_ids: List[str] = Field(default_factory=list)
    contradicted_clause_ids: List[str] = Field(default_factory=list)


def check_grounding(proposal: NegotiationProposal, clauses: List[Clause]) -> GroundingCheckResult:
    """Check that every clause_id in supporting_clauses exists, and that
    numbers in the rationale don't contradict a cited clause's own
    vendor_value (a substring/number heuristic, not exact parsing).
    """
    by_id = {c.clause_id: c for c in clauses if c.clause_id}

    missing = [cid for cid in proposal.supporting_clauses if cid not in by_id]
    if missing:
        return GroundingCheckResult(
            status=GroundingStatus.GROUNDING_FAILED,
            reason=f"Proposal cites unknown clause_id(s): {missing}",
            missing_clause_ids=missing,
        )

    rationale_numbers = {float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", proposal.rationale)}
    contradicted: List[str] = []
    if rationale_numbers:
        for cid in proposal.supporting_clauses:
            value = by_id[cid].vendor_value
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
