"""Legal/Risk Agent: independently assesses legal and compliance risk
across extracted clauses and policy check results, via OpenAI structured
output. Kept separate from Business/Finance (architecture.md, ADR-003)
so the two can genuinely disagree - not merged review logic.
"""

from __future__ import annotations

import json
from typing import List, Optional

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from harness.config import OPENAI_API_KEY, OPENAI_MODEL
from schemas import AgentReview, Clause, PolicyCheckResult, ReviewVerdict

AGENT_NAME = "Legal/Risk Agent"

_SYSTEM_PROMPT = """You are the Legal/Risk Agent in WinWin, a vendor contract
negotiation harness. You independently assess legal and compliance risk
across the extracted contract clauses and the deterministic policy
check results given to you - you do not re-run those checks, you
reason about what they mean.

In your reasoning, name every clause_type whose policy check result is
BLOCKED, CONFLICTING, or CANNOT_VERIFY as a specific concern - do not
just summarize generally. Also flag anything legally risky even if it
technically passed policy (e.g. vague liability language, one-sided
indemnification, ambiguous data-ownership wording).

Verdict rules:
- REJECT if any policy check result has status BLOCKED.
- FLAG if there is no BLOCKED result, but at least one CANNOT_VERIFY,
  CONFLICTING, or LOW_CONFIDENCE result exists.
- ACCEPT only if every policy check result is PASS and you see no other
  material legal risk.

confidence should reflect how confident you are in this verdict given
the evidence quality, not how risky the contract is.
"""


class _ReviewOutput(BaseModel):
    verdict: ReviewVerdict
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)


class LegalRiskAgentError(RuntimeError):
    """Raised when the agent can't produce a valid AgentReview, even after one retry."""


def _format_evidence(clauses: List[Clause], policy_results: List[PolicyCheckResult]) -> str:
    return (
        "Extracted contract clauses:\n"
        f"{json.dumps([c.model_dump(mode='json') for c in clauses], indent=2)}\n\n"
        "Policy check results:\n"
        f"{json.dumps([r.model_dump(mode='json') for r in policy_results], indent=2)}"
    )


def review_legal_risk(
    clauses: List[Clause],
    policy_results: List[PolicyCheckResult],
    client: Optional[OpenAI] = None,
) -> AgentReview:
    """Produce an independent legal/risk AgentReview for the given evidence.

    Validates the model's output; retries once with the error fed back,
    then raises LegalRiskAgentError rather than accepting bad output.
    """
    client = client or OpenAI(api_key=OPENAI_API_KEY)
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

    raise LegalRiskAgentError(
        f"Legal/Risk Agent produced invalid review data after retry: {last_error}"
    )
