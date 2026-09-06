"""Business/Finance Agent: independently assesses business and financial
impact across extracted clauses and policy check results, via OpenAI
structured output. Kept separate from Legal/Risk (architecture.md,
ADR-003) so the two can genuinely disagree - not merged review logic.
"""

from __future__ import annotations

import json
from typing import List, Optional

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from harness.config import OPENAI_MODEL
from schemas import AgentReview, Clause, PolicyCheckResult, ReviewVerdict

AGENT_NAME = "Business/Finance Agent"

_SYSTEM_PROMPT = """You are the Business/Finance Agent in WinWin, a vendor
contract negotiation harness. You independently assess business and
financial impact across the extracted contract clauses and the
deterministic policy check results given to you - you do not re-run
those checks, you reason about what they mean.

Focus on: cost exposure from price escalation and liability terms,
cash-flow impact from payment terms, and operational risk from
termination and SLA terms. In your reasoning, name every clause_type
whose policy check result is BLOCKED, CONFLICTING, or CANNOT_VERIFY as
a specific concern from a business-impact angle, not a legal one. You
may reasonably reach a different verdict than a legal reviewer looking
at the same evidence - that is expected, not an error.

Verdict rules:
- REJECT if any policy check result has status BLOCKED and it creates
  unacceptable financial or operational exposure.
- FLAG if there is no BLOCKED result, but at least one CANNOT_VERIFY,
  CONFLICTING, or LOW_CONFIDENCE result leaves material business
  uncertainty.
- ACCEPT only if every policy check result is PASS and the business
  terms are otherwise sound.

confidence should reflect how confident you are in this verdict given
the evidence quality, not how favorable the contract is.
"""


class _ReviewOutput(BaseModel):
    verdict: ReviewVerdict
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)


class BusinessFinanceAgentError(RuntimeError):
    """Raised when the agent can't produce a valid AgentReview, even after one retry."""


def _format_evidence(clauses: List[Clause], policy_results: List[PolicyCheckResult]) -> str:
    return (
        "Extracted contract clauses:\n"
        f"{json.dumps([c.model_dump(mode='json') for c in clauses], indent=2)}\n\n"
        "Policy check results:\n"
        f"{json.dumps([r.model_dump(mode='json') for r in policy_results], indent=2)}"
    )


def review_business_finance(
    clauses: List[Clause],
    policy_results: List[PolicyCheckResult],
    client: Optional[OpenAI] = None,
) -> AgentReview:
    """Produce an independent business/finance AgentReview for the given evidence.

    Validates the model's output; retries once with the error fed back,
    then raises BusinessFinanceAgentError rather than accepting bad output.
    """
    client = client or OpenAI()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _format_evidence(clauses, policy_results)},
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

    raise BusinessFinanceAgentError(
        f"Business/Finance Agent produced invalid review data after retry: {last_error}"
    )
