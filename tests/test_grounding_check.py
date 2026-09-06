"""Unit tests for the deterministic evidence-grounding check
(harness/grounding_check.py). Covers: valid grounding, an unknown
clause_id, and a rationale number that contradicts the cited clause.
"""

from schemas import CheckStatus, Clause, NegotiationProposal, PolicyCheckResult
from harness.grounding_check import GroundingStatus, check_grounding

ESCALATION_CLAUSE = Clause(
    clause_type="price_escalation",
    vendor_value=8,
    unit="percent",
    source_section="3.1",
    source_text="The annual service fee shall increase by 8% each year.",
    confidence=0.95,
    clause_id="CL-001",
)

PAYMENT_CLAUSE = Clause(
    clause_type="payment_terms_days",
    vendor_value="Net 15",
    source_section="6.1",
    source_text="Vendor invoices are due Net 15 from the invoice date.",
    confidence=0.9,
    clause_id="CL-002",
)

CLAUSES = [ESCALATION_CLAUSE, PAYMENT_CLAUSE]


def test_valid_grounding_passes():
    proposal = NegotiationProposal(
        concessions={"price_escalation": 5},
        rationale="The vendor's stated 8% escalation exceeds our policy; counter at 5%.",
        supporting_clauses=["CL-001"],
    )
    result = check_grounding(proposal, CLAUSES)
    assert result.status == GroundingStatus.PASSED
    assert result.missing_clause_ids == []
    assert result.contradicted_clause_ids == []


def test_unknown_clause_id_fails():
    proposal = NegotiationProposal(
        rationale="Counter at 5% escalation.",
        supporting_clauses=["CL-999"],
    )
    result = check_grounding(proposal, CLAUSES)
    assert result.status == GroundingStatus.GROUNDING_FAILED
    assert "CL-999" in result.missing_clause_ids


def test_rationale_number_mismatch_fails():
    # Cites the 8% clause but claims a different number in the rationale,
    # and it is not one of the proposal's own concessions/requested_changes -
    # so this is a factual misstatement, not a description of a proposed change.
    proposal = NegotiationProposal(
        rationale="The vendor's stated 5% escalation is within an acceptable range.",
        supporting_clauses=["CL-001"],
    )
    result = check_grounding(proposal, CLAUSES)
    assert result.status == GroundingStatus.GROUNDING_FAILED
    assert "CL-001" in result.contradicted_clause_ids


def test_proposed_change_need_not_restate_the_original_value():
    # requested_changes means the rationale is expected to discuss the
    # NEW value (5), not restate the clause's original one (8) - this
    # must pass even though "8" never appears in the rationale text.
    proposal = NegotiationProposal(
        requested_changes={"price_escalation": 5},
        rationale="We propose reducing the escalation to the policy maximum of 5%.",
        supporting_clauses=["CL-001"],
    )
    result = check_grounding(proposal, CLAUSES)
    assert result.status == GroundingStatus.PASSED
    assert result.contradicted_clause_ids == []


def test_conflicting_clause_type_exempt_when_policy_results_given():
    # price_escalation is CONFLICTING - acknowledging the harness's own
    # tie-broken value (5) in the rationale, without it being a formal
    # concession/requested_change, must not be flagged as a wrong fact.
    proposal = NegotiationProposal(
        rationale="Price escalation is conflicting; we accept the conservative 5% pending sign-off.",
        supporting_clauses=["CL-001"],
    )
    policy_results = [
        PolicyCheckResult(
            clause_type="price_escalation",
            status=CheckStatus.CONFLICTING,
            reason="conflicting evidence",
            requires_human_signoff=True,
        )
    ]
    result = check_grounding(proposal, CLAUSES, policy_results)
    assert result.status == GroundingStatus.PASSED
    assert result.contradicted_clause_ids == []
