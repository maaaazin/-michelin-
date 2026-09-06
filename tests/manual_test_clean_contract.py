"""Standalone (non-pytest) manual check that the FINAL approval path is
actually reachable - not just the replan/HUMAN_REVIEW path every other
manual test exercises. Runs a deliberately fully policy-compliant
contract (every clause at or better than data/policy_config.json's
target/hard limit, no contradictions, high-confidence values) through the
REAL compiled graph (harness.graph.run_negotiation - the same call
app/main.py makes). Requires OPENAI_API_KEY in .env; makes real OpenAI
calls. Run:

    python tests/manual_test_clean_contract.py

CLEAN_CONTRACT is also the source text test_docs/clean_pass_demo.pdf was
generated from (via pymupdf) - see tests/manual_test_real_pdfs.py, which
runs the PDF version through the same graph.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.graph import run_negotiation  # noqa: E402
from schemas import NegotiationStage  # noqa: E402

CLEAN_CONTRACT = """MASTER SERVICES AGREEMENT

This Master Services Agreement (the "Agreement") is entered into between
WinWin Manufacturing Ltd. ("Company") and Vendor Corp. ("Vendor").

Section 1 - Annual Contract Value
The total annual contract value payable by Company to Vendor under this
Agreement is USD 1,000,000.

Section 2 - Fees and Price Escalation
The annual service fee shall increase by exactly 3% each year on the
contract anniversary date. No other price escalation of any kind applies
under this Agreement.

Section 3 - Payment Terms
All invoices issued by Vendor are due and payable within 60 days of the
invoice date (Net 60).

Section 4 - Termination
Either party may terminate this Agreement upon 30 days' prior written
notice to the other party.

Section 5 - Liability
Vendor's aggregate liability under this Agreement shall be at least USD
2,000,000, regardless of the theory of liability.

Section 6 - Service Level Agreement
Vendor guarantees a minimum uptime of 99.95% for all services provided
under this Agreement, measured monthly.

Section 7 - Data Ownership
All data submitted to or processed by Vendor under this Agreement remains
the sole and exclusive property of the Company at all times. Vendor
acquires no ownership rights in Company data.

Section 8 - Auto-Renewal
This Agreement automatically renews for successive one-year terms unless
either party provides written notice of non-renewal at least 45 days
before the end of the then-current term.
"""


def main() -> int:
    final_state = run_negotiation(CLEAN_CONTRACT, negotiation_id="NG-CLEAN", contract_id="CTR-CLEAN")

    print("=== AUDIT TRAIL ===")
    for entry in final_state.negotiation_history:
        print(f"  {entry['event']}")
    print()
    print(f"Final state: {final_state.current_state.value}")
    print(f"Replan attempts used: {final_state.replan_count} / 3")

    if final_state.current_state != NegotiationStage.FINAL:
        print("\n*** Did not reach FINAL - see harness/graph.py hard-gate logic and agents/red_team.py. ***")
        return 1
    print("\nReached FINAL - the approval path works for a genuinely compliant contract.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
