"""Standalone (non-pytest) manual check of the Policy Analyst agent
against a real OpenAI call, using an inline sample company-policy
paragraph. Deliberately omits auto_renewal_cancellation_window_days to
confirm the default-fallback path fires for a genuinely absent rule.
Run:

    python tests/manual_test_policy_analyst.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.policy_analyst import extract_policy  # noqa: E402
from schemas import PolicyRuleSource  # noqa: E402

SAMPLE_POLICY = """
Acme Corp - Vendor Negotiation Standards (excerpt)

Pricing: Annual price escalation on renewal should target 3% and must
never exceed 5% under any circumstances.

Payment: Standard payment terms are Net 60. Net 30 is the absolute
minimum acceptable to any vendor.

Termination: Vendors must accept a termination notice period of 30
days as the target; 60 days is the maximum notice period the company
will agree to.

Liability: Vendor's total liability under the agreement must be no
less than the full annual value of the contract.

Service levels: Vendor must commit to at least 99.9% uptime.

Data: All company data processed or stored by the vendor remains the
sole property of Acme Corp at all times; the vendor acquires no
ownership rights.
"""


def main() -> int:
    print("Calling Policy Analyst against the sample policy text...\n")
    config = extract_policy(SAMPLE_POLICY)

    for rule in config.rules:
        print(
            f"{rule.clause_type}: target={rule.target_value} hard_limit={rule.hard_limit_value} "
            f"confidence={rule.confidence:.2f} source={rule.source.value}"
        )

    print("\n=== Checks ===")
    fallback_rule = next(r for r in config.rules if r.clause_type == "auto_renewal_cancellation_window_days")
    print(
        f"[{'OK' if fallback_rule.source == PolicyRuleSource.DEFAULT_FALLBACK else 'CHECK'}] "
        f"auto_renewal_cancellation_window_days source = {fallback_rule.source.value} "
        "(expected default_fallback - deliberately omitted from the sample text)"
    )

    extracted_count = sum(1 for r in config.rules if r.source == PolicyRuleSource.EXTRACTED)
    print(f"[{'OK' if extracted_count >= 5 else 'CHECK'}] {extracted_count} of 7 rules extracted from the document.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
