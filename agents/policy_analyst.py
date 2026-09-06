"""Policy Analyst agent: extracts the company's negotiation policy from
a policy document's raw text via OpenAI structured output.

Design choice: the LLM extracts only the numeric target/hard_limit
values and a confidence score per rule type - the structural fields
(direction, expected_unit, reference_clause_type, description) always
come from the shipped default (data/policy_config.json) as a template.
Those are domain facts (e.g. "lower escalation is better") that do not
vary per company and should not be re-derived from scratch by a model
on every run; only the actual thresholds do.

Below POLICY_RULE_CONFIDENCE_THRESHOLD, or not addressed at all, a rule
falls back to the default template value rather than guessing - this is
the harness's safeguard against silently trusting a weak extraction.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from harness.config import OPENAI_MODEL
from harness.policy_gate import load_policy_config
from schemas import PolicyConfig, PolicyRule, PolicyRuleSource

# Below this, or not found at all, a rule falls back to the config default.
POLICY_RULE_CONFIDENCE_THRESHOLD = 0.7

# The 7 rules data/policy_config.json defines - matches architecture.md.
KNOWN_RULE_TYPES = [
    "price_escalation",
    "payment_terms_days",
    "termination_notice_days",
    "liability_cap",
    "sla_uptime",
    "data_ownership",
    "auto_renewal_cancellation_window_days",
]

# liability_cap (a dynamic reference) and data_ownership (a fixed
# category) have no meaningful number to extract - only their
# found/confidence can move the needle, never target/hard_limit_value.
_NUMERIC_RULE_TYPES = {
    "price_escalation",
    "payment_terms_days",
    "termination_notice_days",
    "sla_uptime",
    "auto_renewal_cancellation_window_days",
}

_SYSTEM_PROMPT = f"""You are the Policy Analyst agent in WinWin, a vendor
contract negotiation harness. Extract the company's negotiation policy
from the policy document text the user provides, for exactly these rule
types: {", ".join(KNOWN_RULE_TYPES)}.

For each rule type, report:
- found: whether the document actually addresses this rule type.
- confidence: how clearly it is stated, 0-1. Below 0.7 for anything
  ambiguous, implicit, or only weakly implied. Do not default to a high
  score out of habit.
- target_value and hard_limit_value: the numeric preferred and hard
  boundary values, for price_escalation (percent), payment_terms_days,
  termination_notice_days, and auto_renewal_cancellation_window_days
  (days), and sla_uptime (percent).

Leave target_value and hard_limit_value null for liability_cap and
data_ownership - those are not simple numbers. For those two, just
report found and confidence for whether the document confirms that
vendor liability must be at least the contract's annual value, and
that data ownership must remain with the company, respectively.

If a rule type is not addressed at all, set found=false - do not guess
a value.
"""


class _ExtractedRuleConfidence(BaseModel):
    clause_type: str
    found: bool
    confidence: float = Field(ge=0.0, le=1.0)
    target_value: Optional[float] = None
    hard_limit_value: Optional[float] = None


class _PolicyExtractionOutput(BaseModel):
    rules: List[_ExtractedRuleConfidence]


class PolicyAnalystError(RuntimeError):
    """Raised when the agent can't produce valid extraction data, even after one retry."""


def extract_policy(
    policy_text: str,
    default_config: Optional[PolicyConfig] = None,
    client: Optional[OpenAI] = None,
) -> PolicyConfig:
    """Extract a company PolicyConfig from raw policy document text.

    See the module docstring for the extraction-vs-template split and
    the fallback rule. Validates the model's output; retries once with
    the error fed back, then raises PolicyAnalystError.
    """
    default_config = default_config or load_policy_config()
    defaults_by_type: Dict[str, PolicyRule] = {r.clause_type: r for r in default_config.rules}

    client = client or OpenAI()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": policy_text},
    ]

    last_error: Optional[str] = None
    extracted_by_type: Dict[str, _ExtractedRuleConfidence] = {}
    got_valid_output = False
    for _ in range(2):
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
                response_format=_PolicyExtractionOutput,
            )
            message = completion.choices[0].message
            if message.parsed is None:
                last_error = f"model refused or returned nothing: {message.refusal}"
                continue
            extracted_by_type = {r.clause_type: r for r in message.parsed.rules}
            got_valid_output = True
            break
        except ValidationError as e:
            last_error = str(e)
            continue

    if not got_valid_output:
        raise PolicyAnalystError(
            f"Policy Analyst produced invalid extraction data after retry: {last_error}"
        )

    return _build_policy_config(default_config, defaults_by_type, extracted_by_type)


def _is_usable(clause_type: str, entry: Optional[_ExtractedRuleConfidence]) -> bool:
    """Whether an extracted entry clears the bar to use instead of the
    default. A numeric rule needs at least one of target/hard_limit - a
    document that states one threshold ("at least 99.9% uptime") with
    no separate target is still usable; see _resolve_numeric_values.
    """
    if entry is None or not entry.found or entry.confidence < POLICY_RULE_CONFIDENCE_THRESHOLD:
        return False
    if clause_type in _NUMERIC_RULE_TYPES:
        return entry.target_value is not None or entry.hard_limit_value is not None
    return True


def _resolve_numeric_values(entry: _ExtractedRuleConfidence) -> tuple:
    """If only one of target/hard_limit was given, use it for both - a
    single stated threshold is both the aspiration and the floor.
    """
    target = entry.target_value if entry.target_value is not None else entry.hard_limit_value
    hard_limit = entry.hard_limit_value if entry.hard_limit_value is not None else entry.target_value
    return target, hard_limit


def _build_policy_config(
    default_config: PolicyConfig,
    defaults_by_type: Dict[str, PolicyRule],
    extracted_by_type: Dict[str, _ExtractedRuleConfidence],
) -> PolicyConfig:
    """Merge extracted values onto the default template, rule by rule -
    factored out so tests/test_policy_analyst_fallback.py can exercise
    the fallback logic directly without a live API call.
    """
    new_rules: List[PolicyRule] = []
    for clause_type in KNOWN_RULE_TYPES:
        template = defaults_by_type.get(clause_type)
        if template is None:
            continue  # shouldn't happen with the shipped default config
        entry = extracted_by_type.get(clause_type)

        if _is_usable(clause_type, entry):
            assert entry is not None
            if clause_type in _NUMERIC_RULE_TYPES:
                target, hard_limit = _resolve_numeric_values(entry)
            else:
                target, hard_limit = template.target_value, template.hard_limit_value
            new_rules.append(
                template.model_copy(
                    update={
                        "target_value": target,
                        "hard_limit_value": hard_limit,
                        "confidence": entry.confidence,
                        "source": PolicyRuleSource.EXTRACTED,
                    }
                )
            )
        else:
            new_rules.append(
                template.model_copy(update={"confidence": 1.0, "source": PolicyRuleSource.DEFAULT_FALLBACK})
            )

    return PolicyConfig(version=default_config.version, rules=new_rules)
