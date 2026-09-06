"""Standalone (non-pytest) manual check of the Contract Analyst agent
against a real OpenAI call. Run directly:

    python tests/manual_test_contract_analyst.py

Requires OPENAI_API_KEY in .env or the environment. Not part of the
pytest suite - it costs real API calls and its output needs a human to
read, not an assertion to grade.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.contract_analyst import ContractAnalystError, extract_clauses  # noqa: E402

SAMPLE_CONTRACT = """
MASTER SERVICES AGREEMENT (excerpt)

Section 3.1 - Fees
The annual service fee shall increase by 8% each year on the contract
anniversary date, unless otherwise adjusted under Section 4.2 or
Appendix B below.

Section 4.2 - Escalation Cap
Notwithstanding Section 3.1, annual escalation shall not exceed 5%.

Section 6.1 - Payment
Vendor invoices are due Net 15 from the invoice date.

Section 9 - Termination
Either party may terminate this Agreement upon 90 days' written notice.

Appendix B - Renewal Terms
At each renewal, Vendor may increase fees by up to 15% over the prior
year's fees, at Vendor's sole discretion.

This Agreement is silent on service level commitments; no uptime or
availability guarantee is provided by Vendor.
"""


def main() -> int:
    print("Calling Contract Analyst against the sample contract...\n")
    try:
        clauses = extract_clauses(SAMPLE_CONTRACT)
    except ContractAnalystError as e:
        print(f"FAILED: {e}")
        return 1

    print(f"Got {len(clauses)} clause(s):\n")
    for clause in clauses:
        print(clause.model_dump_json(indent=2))
        print("-" * 60)

    # Human-readable checks, not hard asserts - this script is for
    # eyeballing real model output, per the task's instructions.
    escalation = [c for c in clauses if c.clause_type == "price_escalation"]
    sla = [c for c in clauses if c.clause_type == "sla_uptime"]
    payment = [c for c in clauses if c.clause_type == "payment_terms_days"]

    print("\n=== Checks ===")
    print(
        f"[{'OK' if len(escalation) >= 2 else 'CHECK'}] "
        f"price_escalation returned as {len(escalation)} separate entrie(s) "
        f"(expect >= 2, not merged): values = {[c.vendor_value for c in escalation]}"
    )
    print(
        f"[{'OK' if sla and sla[0].not_specified else 'CHECK'}] "
        f"sla_uptime not_specified = {sla[0].not_specified if sla else 'MISSING ENTRY'}"
    )
    print(
        f"[{'OK' if payment and payment[0].vendor_value else 'CHECK'}] "
        f"payment_terms_days = {payment[0].vendor_value if payment else 'MISSING ENTRY'}"
    )

    # Hard assertion: the sample contract has exactly three escalation
    # mentions (3.1, 4.2, Appendix B). Fail loudly if recall regresses.
    if len(escalation) != 3:
        raise AssertionError(
            f"Expected 3 separate price_escalation entries (3.1, 4.2, "
            f"Appendix B), got {len(escalation)}: "
            f"{[(c.source_section, c.vendor_value) for c in escalation]}"
        )
    print("[OK] price_escalation has exactly 3 separate entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
