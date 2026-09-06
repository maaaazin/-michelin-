"""Red-Team Agent: independently challenges the Negotiation Agent's
proposal via OpenAI structured output. Its job is the reasoning-level
second opinion a deterministic check cannot do - it does not re-run
harness/grounding_check.py's logic, which already handles citation and
number-consistency checks separately.
"""

from __future__ import annotations

import json
from typing import List, Optional

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from harness.config import OPENAI_MODEL
from schemas import AgentReview, Clause, NegotiationProposal, PolicyCheckResult, ReviewVerdict

AGENT_NAME = "Red-Team Agent"

_SYSTEM_PROMPT = """You are the Red-Team Agent in WinWin, a vendor contract
negotiation harness. Your job is to independently challenge the
Negotiation Agent's proposal, not rubber-stamp it - actively look for
reasons to reject.

Check for: policy check results (BLOCKED, CONFLICTING, CANNOT_VERIFY,
LOW_CONFIDENCE) the proposal doesn't actually resolve; claims in the
rationale unsupported by the cited clauses; risks the Legal/Risk or
Business/Finance reviews raised that the proposal ignores; contradictions
the proposal glossed over instead of addressing; concessions beyond what
is needed to reach compliance; and inconsistency between what the
proposal claims and what the two prior reviews found.

Do not re-check whether every cited clause_id exists or whether a
number matches a clause verbatim - that is a deterministic check the
harness already runs separately. Your value is the reasoning-level
second opinion that check cannot do: whether the proposal is actually
sound, not just well-cited.

Verdict REJECT if you find a real, specific problem with the proposal.
Verdict ACCEPT only if it genuinely resolves the flagged issues without
introducing a new one.
"""


class _ReviewOutput(BaseModel):
    verdict: ReviewVerdict
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)


class RedTeamAgentError(RuntimeError):
    """Raised when the agent can't produce a valid AgentReview, even after one retry."""


def _format_context(
    proposal: NegotiationProposal,
    clauses: List[Clause],
    policy_results: List[PolicyCheckResult],
    legal_review: AgentReview,
    business_review: AgentReview,
) -> str:
    return (
        "Negotiation proposal under review:\n"
        f"{proposal.model_dump_json(indent=2)}\n\n"
        "Extracted contract clauses:\n"
        f"{json.dumps([c.model_dump(mode='json') for c in clauses], indent=2)}\n\n"
        "Policy check results:\n"
        f"{json.dumps([r.model_dump(mode='json') for r in policy_results], indent=2)}\n\n"
        "Legal/Risk Agent review:\n"
        f"{legal_review.model_dump_json(indent=2)}\n\n"
        "Business/Finance Agent review:\n"
        f"{business_review.model_dump_json(indent=2)}"
    )


def review_red_team(
    proposal: NegotiationProposal,
    clauses: List[Clause],
    policy_results: List[PolicyCheckResult],
    legal_review: AgentReview,
    business_review: AgentReview,
    client: Optional[OpenAI] = None,
) -> AgentReview:
    """Produce an independent Red-Team AgentReview of a proposal.

    Validates the model's output; retries once with the error fed back,
    then raises RedTeamAgentError rather than accepting bad output.
    """
    client = client or OpenAI()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _format_context(proposal, clauses, policy_results, legal_review, business_review),
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
                response_format=_ReviewOutput,
            )
            message = completion.choices[0].message
            if message.parsed is None:
                last_error = f"model refused or returned nothing: {message.refusal}"
                continue
            parsed = message.parsed
        except ValidationError as e:
            last_error = str(e)
            continue

        return AgentReview(
            agent_name=AGENT_NAME,
            verdict=parsed.verdict,
            reasoning=parsed.reasoning,
            confidence=parsed.confidence,
        )

    raise RedTeamAgentError(
        f"Red-Team Agent produced invalid review data after retry: {last_error}"
    )
