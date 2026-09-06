"""Contract Analyst agent: extracts structured Clause evidence from raw
vendor contract text via the OpenAI API. Uses structured outputs (a
Pydantic response schema), not prompt-only JSON, so results are
schema-constrained before Clause's own validators even run.
"""

from __future__ import annotations

from typing import List, Optional

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from harness.config import OPENAI_MODEL
from schemas import Clause

# Clause types the policy engine governs (data/policy_config.json). The
# model may also return others; those just aren't checked against policy.
KNOWN_CLAUSE_TYPES = [
    "price_escalation",
    "payment_terms_days",
    "termination_notice_days",
    "liability_cap",
    "annual_contract_value",
    "sla_uptime",
    "data_ownership",
    "auto_renewal_cancellation_window_days",
]

_SYSTEM_PROMPT = f"""You are the Contract Analyst agent in Warden, a vendor
contract negotiation harness. Extract structured evidence from the
vendor contract text the user provides.

For each of these known clause types, find every place the contract
addresses it and return one entry per distinct mention:
{", ".join(KNOWN_CLAUSE_TYPES)}.

Rules:
- If a clause type is not addressed anywhere in the contract, return
  ONE entry for it with not_specified=true, vendor_value=null,
  unit=null, source_section=null, source_text=null, and a high
  confidence (0.9+) reflecting confidence it is genuinely absent, not
  that you failed to find it.
- If a clause type is addressed in more than one place with different
  values (a contradiction), return a SEPARATE entry per mention - never
  merge them or silently pick one.
- vendor_value is a plain number for numeric clauses (e.g. 8 for "8%"),
  duration text like "Net 30" or "180 days" for duration clauses, and
  free text for categorical clauses like data ownership.
- unit describes the value, e.g. "percent", "days", "INR"; null for
  text/categorical values.
- source_section is the contract's own section/clause label (e.g.
  "4.2", "Appendix B"). source_text is the verbatim source sentence(s).
- confidence must be honest: below 0.6 when the source text is
  ambiguous, implicit, or only weakly implies the value. Do not default
  to a high score out of habit.
- You may also return other clause types you find materially relevant,
  beyond the known list, using a clear descriptive clause_type string.
"""


class _ExtractedClauses(BaseModel):
    clauses: List[Clause]


class ContractAnalystError(RuntimeError):
    """Raised when the agent can't produce valid Clause data, even after one retry."""


def extract_clauses(contract_text: str, client: Optional[OpenAI] = None) -> List[Clause]:
    """Extract structured Clause evidence from raw contract text.

    Validates every item against the Clause schema. On a validation
    failure, retries once with the error fed back to the model, then
    raises ContractAnalystError rather than silently dropping a clause.
    """
    client = client or OpenAI()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": contract_text},
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
                response_format=_ExtractedClauses,
            )
            message = completion.choices[0].message
            if message.parsed is None:
                last_error = f"model refused or returned nothing: {message.refusal}"
                continue
            clauses = list(message.parsed.clauses)
        except ValidationError as e:
            last_error = str(e)
            continue

        for i, clause in enumerate(clauses, start=1):
            if not clause.clause_id:
                clause.clause_id = f"CL-{i:03d}"
        return clauses

    raise ContractAnalystError(
        f"Contract Analyst produced invalid Clause data after retry: {last_error}"
    )
