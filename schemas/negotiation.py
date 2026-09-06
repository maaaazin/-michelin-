"""Negotiation-side schemas: proposals, independent agent reviews, and
the overall negotiation state tracked outside any single LLM call's
context window.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .clause import Clause, ClauseValue
from .policy import PolicyCheckResult, PolicyConfig


class NegotiationStage(str, Enum):
    """The state machine stages from architecture.md, Section 6, plus
    HUMAN_REVIEW: the graceful-degradation terminal state when the
    replan loop exceeds its attempt limit (harness/graph.py).
    """

    POLICY_EXTRACTION = "POLICY_EXTRACTION"
    CONTRACT_ANALYSIS = "CONTRACT_ANALYSIS"
    POLICY_CHECK = "POLICY_CHECK"
    NEGOTIATION_PLANNING = "NEGOTIATION_PLANNING"
    RED_TEAM_REVIEW = "RED_TEAM_REVIEW"
    POLICY_GATE = "POLICY_GATE"
    REPLAN = "REPLAN"
    FINAL = "FINAL"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class ReviewVerdict(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    FLAG = "FLAG"


class NegotiationProposal(BaseModel):
    """A proposed negotiation move.

    supporting_clauses must be clause_id references, not free text, so
    claims trace back to real evidence; validating the ids actually
    exist happens in the harness, not here.
    """

    concessions: Dict[str, ClauseValue] = Field(
        default_factory=dict,
        description="Terms the company offers to give, keyed by clause_type.",
    )
    requested_changes: Dict[str, ClauseValue] = Field(
        default_factory=dict,
        description="Terms the company asks the vendor to change, keyed by clause_type.",
    )
    rationale: str
    supporting_clauses: List[str] = Field(
        default_factory=list,
        description="clause_id references backing this proposal's claims.",
    )


class AgentReview(BaseModel):
    """An independent agent's verdict on a proposal (e.g. the Red-Team Agent)."""

    agent_name: str
    verdict: ReviewVerdict
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)


class NegotiationState(BaseModel):
    """The single source of truth for one negotiation.

    Deliberately not the LLM's conversational context - every agent
    reads and writes this explicitly, per architecture.md Section 5.4.
    """

    negotiation_id: str
    contract_id: str
    policy_version: str
    contract_text: Optional[str] = Field(
        default=None,
        description="Raw contract text for the graph's first node (Contract Analyst) to read.",
    )
    policy_text: Optional[str] = Field(
        default=None,
        description=(
            "Raw company-policy document text, if one was uploaded. None means "
            "use the constraints PolicyConfig as-is (the default_config.json path)."
        ),
    )
    replan_count: int = Field(
        default=0,
        description="Replan iterations used so far - the graph's max-replan safeguard reads this.",
    )
    current_offer: Optional[NegotiationProposal] = None
    vendor_position: Dict[str, ClauseValue] = Field(default_factory=dict)
    company_position: Dict[str, ClauseValue] = Field(default_factory=dict)
    extracted_clauses: List[Clause] = Field(default_factory=list)
    constraints: PolicyConfig
    violations: List[PolicyCheckResult] = Field(default_factory=list)
    negotiation_history: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Append-only round log: one entry per round with the proposal "
            "made, checks run, and outcome."
        ),
    )
    agent_reviews: List[AgentReview] = Field(default_factory=list)
    current_state: NegotiationStage = NegotiationStage.CONTRACT_ANALYSIS
