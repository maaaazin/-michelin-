"""Unit tests for the deterministic evidence-grounding check
(harness/grounding_check.py). Covers: valid grounding, an unknown
clause_id, and a rationale number that contradicts the cited clause.
"""

from schemas import Clause, NegotiationProposal
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
    # Cites the 8% clause but claims a different number in the rationale.
    proposal = NegotiationProposal(
        rationale="The vendor's stated 5% escalation is within an acceptable range.",
        supporting_clauses=["CL-001"],
    )
    result = check_grounding(proposal, CLAUSES)
    assert result.status == GroundingStatus.GROUNDING_FAILED
    assert "CL-001" in result.contradicted_clause_ids
