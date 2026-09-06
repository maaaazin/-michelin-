"""LangGraph wiring for the full negotiation state machine
(architecture.md Section 6): CONTRACT_ANALYSIS -> POLICY_CHECK ->
NEGOTIATION_PLANNING -> RED_TEAM_REVIEW -> POLICY_GATE -> (PASS: FINAL
| FAIL: REPLAN back to NEGOTIATION_PLANNING, capped at MAX_REPLANS,
after which it escalates to HUMAN_REVIEW instead of looping forever).

Legal/Risk and Business/Finance run once, between POLICY_CHECK and the
first NEGOTIATION_PLANNING - a replan loops policy_gate_final straight
back to negotiation_planning, never touching those review nodes again.

Not re-exported from harness/__init__.py on purpose: this module pulls
in agents (and therefore openai) and langgraph, which the lightweight
harness unit tests (policy_gate, grounding_check) don't need. Import it
directly: `from harness.graph import run_negotiation`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from langgraph.graph import END, StateGraph

from agents.business_finance import review_business_finance
from agents.contract_analyst import extract_clauses
from agents.legal_risk import review_legal_risk
from agents.negotiation import negotiate
from agents.red_team import review_red_team
from harness.policy_gate import load_policy_config, run_policy_check
from schemas import (
    AgentReview,
    CheckStatus,
    NegotiationStage,
    NegotiationState,
    PolicyConfig,
    ReviewVerdict,
)

# Max replan attempts before escalating to HUMAN_REVIEW instead of looping.
MAX_REPLANS = 3


def _latest_review(reviews: List[AgentReview], agent_name: str) -> Optional[AgentReview]:
    """Most recent review from one named agent, or None if it hasn't run."""
    for review in reversed(reviews):
        if review.agent_name == agent_name:
            return review
    return None


def _gate_outcome(state: NegotiationState) -> tuple[bool, List[Any], Optional[AgentReview]]:
    """Shared by the gate node and its router: recompute the policy
    check against the current proposal (cheap, deterministic, no LLM)
    and pair it with the latest Red-Team verdict.
    """
    results = run_policy_check(state.extracted_clauses, state.constraints, proposal=state.current_offer)
    hard_fail = any(r.status in (CheckStatus.BLOCKED, CheckStatus.CONFLICTING) for r in results)
    red_team = _latest_review(state.agent_reviews, "Red-Team Agent")
    red_team_rejected = red_team is not None and red_team.verdict == ReviewVerdict.REJECT
    passed = not hard_fail and not red_team_rejected
    return passed, results, red_team


def contract_analysis_node(state: NegotiationState) -> Dict[str, Any]:
    clauses = extract_clauses(state.contract_text or "")
    return {
        "extracted_clauses": clauses,
        "current_state": NegotiationStage.CONTRACT_ANALYSIS,
        "negotiation_history": state.negotiation_history
        + [{"event": f"Contract uploaded; {len(clauses)} clause(s) extracted."}],
    }


def policy_check_node(state: NegotiationState) -> Dict[str, Any]:
    results = run_policy_check(state.extracted_clauses, state.constraints)
    counts: Dict[str, int] = {}
    for r in results:
        counts[r.status.value] = counts.get(r.status.value, 0) + 1
    summary = ", ".join(f"{v} {k}" for k, v in counts.items())
    return {
        "violations": results,
        "current_state": NegotiationStage.POLICY_CHECK,
        "negotiation_history": state.negotiation_history + [{"event": f"Policy check complete: {summary}."}],
    }


def initial_reviews_node(state: NegotiationState) -> Dict[str, Any]:
    legal_review = review_legal_risk(state.extracted_clauses, state.violations)
    business_review = review_business_finance(state.extracted_clauses, state.violations)
    return {
        "agent_reviews": state.agent_reviews + [legal_review, business_review],
        "negotiation_history": state.negotiation_history
        + [
            {"event": f"Legal/Risk review: {legal_review.verdict.value}."},
            {"event": f"Business/Finance review: {business_review.verdict.value}."},
        ],
    }


def negotiation_planning_node(state: NegotiationState) -> Dict[str, Any]:
    legal_review = _latest_review(state.agent_reviews, "Legal/Risk Agent")
    business_review = _latest_review(state.agent_reviews, "Business/Finance Agent")

    replan_context = None
    if state.replan_count > 0:
        for entry in reversed(state.negotiation_history):
            if entry.get("rejection_context"):
                replan_context = entry["event"]
                break

    proposal = negotiate(
        state.extracted_clauses,
        state.violations,
        legal_review,
        business_review,
        replan_context=replan_context,
    )
    line = (
        "Negotiation strategy generated."
        if state.replan_count == 0
        else f"Negotiation strategy regenerated (attempt {state.replan_count})."
    )
    return {
        "current_offer": proposal,
        "current_state": NegotiationStage.NEGOTIATION_PLANNING,
        "negotiation_history": state.negotiation_history + [{"event": line}],
    }


def red_team_review_node(state: NegotiationState) -> Dict[str, Any]:
    legal_review = _latest_review(state.agent_reviews, "Legal/Risk Agent")
    business_review = _latest_review(state.agent_reviews, "Business/Finance Agent")
    review = review_red_team(
        state.current_offer, state.extracted_clauses, state.violations, legal_review, business_review
    )
    return {
        "agent_reviews": state.agent_reviews + [review],
        "current_state": NegotiationStage.RED_TEAM_REVIEW,
        "negotiation_history": state.negotiation_history
        + [{"event": f"Red-Team {review.verdict.value}: {review.reasoning}"}],
    }


def policy_gate_final_node(state: NegotiationState) -> Dict[str, Any]:
    passed, results, red_team = _gate_outcome(state)
    summary = "; ".join(f"{r.clause_type}={r.status.value}" for r in results)
    red_team_word = red_team.verdict.value if red_team else "n/a"

    if passed:
        line = f"Policy gate PASSED ({summary}); Red-Team {red_team_word}. Final proposal approved."
        return {
            "current_state": NegotiationStage.POLICY_GATE,
            "negotiation_history": state.negotiation_history + [{"event": line}],
        }

    reasons = [f"{r.clause_type} {r.status.value}: {r.reason}" for r in results if r.status in (CheckStatus.BLOCKED, CheckStatus.CONFLICTING)]
    if red_team and red_team.verdict == ReviewVerdict.REJECT:
        reasons.append(f"Red-Team REJECT: {red_team.reasoning}")
    rejection_summary = (
        "Previous proposal rejected. " + " ".join(reasons) + " Generate an alternative strategy that resolves these issues."
    )
    new_count = state.replan_count + 1
    fail_line = f"Policy gate FAILED ({summary}); Red-Team {red_team_word}. Replanning (attempt {new_count})."
    return {
        "current_state": NegotiationStage.POLICY_GATE,
        "replan_count": new_count,
        "negotiation_history": state.negotiation_history
        + [{"event": fail_line}, {"event": rejection_summary, "rejection_context": True}],
    }


def finalize_node(state: NegotiationState) -> Dict[str, Any]:
    return {
        "current_state": NegotiationStage.FINAL,
        "negotiation_history": state.negotiation_history + [{"event": "Final proposal approved."}],
    }


def escalate_node(state: NegotiationState) -> Dict[str, Any]:
    line = f"Max replan attempts ({MAX_REPLANS}) exceeded - escalating to human review."
    return {
        "current_state": NegotiationStage.HUMAN_REVIEW,
        "negotiation_history": state.negotiation_history + [{"event": line}],
    }


def _route_after_policy_gate(state: NegotiationState) -> str:
    passed, _results, _red_team = _gate_outcome(state)
    if passed:
        return "final"
    if state.replan_count >= MAX_REPLANS:
        return "human_review"
    return "replan"


def build_graph():
    """Compile the negotiation graph. Call run_negotiation() for the
    convenient one-shot entry point; use this directly if you need to
    invoke/stream a graph with a caller-built initial state.
    """
    graph = StateGraph(NegotiationState)
    graph.add_node("contract_analysis", contract_analysis_node)
    graph.add_node("policy_check", policy_check_node)
    graph.add_node("initial_reviews", initial_reviews_node)
    graph.add_node("negotiation_planning", negotiation_planning_node)
    graph.add_node("red_team_review", red_team_review_node)
    graph.add_node("policy_gate_final", policy_gate_final_node)
    graph.add_node("finalize", finalize_node)
    graph.add_node("escalate", escalate_node)

    graph.set_entry_point("contract_analysis")
    graph.add_edge("contract_analysis", "policy_check")
    graph.add_edge("policy_check", "initial_reviews")
    graph.add_edge("initial_reviews", "negotiation_planning")
    graph.add_edge("negotiation_planning", "red_team_review")
    graph.add_edge("red_team_review", "policy_gate_final")
    graph.add_conditional_edges(
        "policy_gate_final",
        _route_after_policy_gate,
        {"final": "finalize", "replan": "negotiation_planning", "human_review": "escalate"},
    )
    graph.add_edge("finalize", END)
    graph.add_edge("escalate", END)

    return graph.compile()


def run_negotiation(
    contract_text: str,
    negotiation_id: str = "NG-001",
    contract_id: str = "CTR-001",
    policy: Optional[PolicyConfig] = None,
) -> NegotiationState:
    """One-shot entry point: build the initial state, run the compiled
    graph end to end, and return a typed NegotiationState.
    """
    policy = policy or load_policy_config()
    initial_state = NegotiationState(
        negotiation_id=negotiation_id,
        contract_id=contract_id,
        policy_version=policy.version,
        contract_text=contract_text,
        constraints=policy,
    )
    result = build_graph().invoke(initial_state)
    return NegotiationState.model_validate(result)
