"""Contract Analyst agent: extracts structured Clause evidence from raw
vendor contract text via the OpenAI API. Uses structured outputs (a
Pydantic response schema), not prompt-only JSON, so results are
schema-constrained before Clause's own validators even run.
"""

from __future__ import annotations

import re
import warnings
from typing import List, Optional, Set

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from harness.config import OPENAI_MODEL
from schemas import Clause

# Total attempts (1 initial + retries) before giving up on schema validity.
MAX_ATTEMPTS = 3

_CROSS_REF_PATTERN = re.compile(r"\b(Section\s+[\dA-Za-z.]+|Appendix\s+[A-Z]+)\b", re.IGNORECASE)
_LABEL_PREFIX = re.compile(r"^(section|appendix)\s+", re.IGNORECASE)


def _normalize_label(label: str) -> str:
    """Strip a leading 'Section '/'Appendix ' so '4.2' (a stored
    source_section) and 'Section 4.2' (a regex match) compare equal.
    """
    return _LABEL_PREFIX.sub("", label.strip()).strip().lower()

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

Scan the ENTIRE contract text, including every appendix and exhibit, not
just numbered sections - a clause is often overridden or extended there.
If one passage cross-references another (e.g. "unless otherwise adjusted
under Section 4.2 or Appendix B"), treat that as an instruction to go
find and extract those referenced passages too, not a reason to skip them.

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
    """Raised when the agent can't produce valid Clause data, even after retrying."""


def _describe_validation_error(error: ValidationError) -> str:
    """Turn a Clause ValidationError into a per-field description for
    the retry prompt. The not_specified/vendor_value pairing is now
    auto-normalized in the schema itself (schemas/clause.py), not
    raised, so this only fires for genuine shape errors (bad type,
    out-of-range confidence, a missing required field).
    """
    parts = [f"At {'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in error.errors()]
    return " ".join(parts)


def _find_unaddressed_cross_references(clauses: List[Clause]) -> List[str]:
    """Find Section/Appendix references inside source_text that were
    never themselves used as a source_section - a sign the model named
    a cross-reference but never actually went and extracted it.
    """
    covered: Set[str] = {_normalize_label(c.source_section) for c in clauses if c.source_section}
    referenced: Set[str] = set()
    for clause in clauses:
        if not clause.source_text:
            continue
        for match in _CROSS_REF_PATTERN.findall(clause.source_text):
            if _normalize_label(match) not in covered:
                referenced.add(match.strip())
    return sorted(referenced)


def extract_clauses(contract_text: str, client: Optional[OpenAI] = None) -> List[Clause]:
    """Extract structured Clause evidence from raw contract text.

    Validates every item against the Clause schema and retries with a
    specific corrective message on failure. Also checks that every
    Section/Appendix a clause's source_text references was itself
    extracted; if not, retries with that gap named too. Raises
    ContractAnalystError only on a genuine schema failure after
    MAX_ATTEMPTS - an unresolved cross-reference after all attempts is
    logged as a warning and returned as best-effort, not fatal.
    """
    client = client or OpenAI()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": contract_text},
    ]

    last_error: Optional[str] = None
    for attempt in range(MAX_ATTEMPTS):
        if last_error:
            messages.append(
                {
                    "role": "user",
                    "content": f"Your previous output was invalid: {last_error} Return corrected structured output.",
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
            last_error = _describe_validation_error(e)
            continue

        missing_refs = _find_unaddressed_cross_references(clauses)
        if missing_refs and attempt < MAX_ATTEMPTS - 1:
            last_error = (
                f"Your source_text mentions {missing_refs} but no clause entry has "
                f"one of those as its own source_section. Go read those passages "
                "and add the missing entries - don't just cite them in passing."
            )
            continue
        if missing_refs:
            warnings.warn(
                f"Contract Analyst: cross-references left unaddressed after "
                f"{MAX_ATTEMPTS} attempts: {missing_refs}",
                stacklevel=2,
            )

        for i, clause in enumerate(clauses, start=1):
            if not clause.clause_id:
                clause.clause_id = f"CL-{i:03d}"
        return clauses

    raise ContractAnalystError(
        f"Contract Analyst produced invalid Clause data after {MAX_ATTEMPTS} attempts: {last_error}"
    )
