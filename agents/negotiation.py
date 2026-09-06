"""Negotiation Agent: proposes a negotiation strategy grounded in the
extracted evidence and informed by the Legal/Risk and Business/Finance
reviews, via OpenAI structured output. An accepted proposal has already
passed harness/grounding_check.py, not just been asked nicely to cite
its sources.

concessions/requested_changes are modeled here as a list of
{clause_type, value} items rather than a raw dict: OpenAI's structured
outputs (strict mode) don't support open-ended object keys, only fixed
schemas. The list is converted to the dict NegotiationProposal expects
after parsing.
"""

from __future__ import annotations

import json
from typing import List, Optional

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from harness.config import OPENAI_MODEL
from harness.grounding_check import GroundingStatus, check_grounding
from schemas import AgentReview, Clause, ClauseValue, NegotiationProposal, PolicyCheckResult

_SYSTEM_PROMPT = """You are the Negotiation Agent in WinWin, a vendor contract
negotiation harness. Propose a negotiation strategy using only the
extracted clauses, policy check results, and the two independent agent
reviews given to you below.

Address every policy check result that is not PASS: propose a
concession or requested change that resolves BLOCKED violations, and
acknowledge CANNOT_VERIFY / CONFLICTING / LOW_CONFIDENCE results in your
rationale rather than ignoring them. Take the Legal/Risk and
Business/Finance reviews' concerns into account.

Ground every factual claim in a cited clause_id. Never state a number
or fact that is not present in the clauses you were given. concessions
and requested_changes each list one entry per clause_type you are
proposing a value for.

You have no authority to override company policy - propose the most
favorable compliant position, not what the vendor originally offered.
"""


class _ValueItem(BaseModel):
    clause_type: str
    value: ClauseValue


class _NegotiationOutput(BaseModel):
    concessions: List[_ValueItem]
    requested_changes: List[_ValueItem]
    rationale: str
    supporting_clauses: List[str]


class NegotiationAgentError(RuntimeError):
    """Raised when the agent can't produce a valid, grounded NegotiationProposal, even after one retry."""


def _format_context(
    clauses: List[Clause],
    policy_results: List[PolicyCheckResult],
    legal_review: AgentReview,
    business_review: AgentReview,
    replan_context: Optional[str] = None,
) -> str:
    context = (
        "Extracted contract clauses:\n"
        f"{json.dumps([c.model_dump(mode='json') for c in clauses], indent=2)}\n\n"
        "Policy check results:\n"
        f"{json.dumps([r.model_dump(mode='json') for r in policy_results], indent=2)}\n\n"
        "Legal/Risk Agent review:\n"
        f"{legal_review.model_dump_json(indent=2)}\n\n"
        "Business/Finance Agent review:\n"
        f"{business_review.model_dump_json(indent=2)}"
    )
    if replan_context:
        context += f"\n\n{replan_context}"
    return context


def negotiate(
    clauses: List[Clause],
    policy_results: List[PolicyCheckResult],
    legal_review: AgentReview,
    business_review: AgentReview,
    client: Optional[OpenAI] = None,
    replan_context: Optional[str] = None,
) -> NegotiationProposal:
    """Produce a NegotiationProposal grounded in the given evidence.

    Validates schema shape, then runs harness/grounding_check.py before
    accepting the result - a grounding failure is fed back to the model
    exactly like a schema validation failure, with one retry before
    raising NegotiationAgentError.

    replan_context, if given, is appended to the prompt - the harness
    graph passes the prior rejection reason here so a replanned proposal
    is told exactly what failed and why, per architecture.md's example.
    """
    client = client or OpenAI()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _format_context(clauses, policy_results, legal_review, business_review, replan_context),
        },
    ]

    last_error: Optional[str] = None
    for _ in range(2):
        if last_error:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your previous output was invalid: {last_error}. "
                        "Return corrected structured output."
                    ),
                }
            )
        try:
            completion = client.chat.completions.parse(
                model=OPENAI_MODEL,
                messages=messages,
                response_format=_NegotiationOutput,
            )
            message = completion.choices[0].message
            if message.parsed is None:
                last_error = f"model refused or returned nothing: {message.refusal}"
                continue
            parsed = message.parsed
            proposal = NegotiationProposal(
                concessions={item.clause_type: item.value for item in parsed.concessions},
                requested_changes={item.clause_type: item.value for item in parsed.requested_changes},
                rationale=parsed.rationale,
                supporting_clauses=parsed.supporting_clauses,
            )
        except ValidationError as e:
            last_error = str(e)
            continue

        grounding = check_grounding(proposal, clauses, policy_results)
        if grounding.status != GroundingStatus.PASSED:
            last_error = f"grounding check failed: {grounding.reason}"
            continue

        return proposal

    raise NegotiationAgentError(
        f"Negotiation Agent produced an invalid or ungrounded proposal after retry: {last_error}"
    )
