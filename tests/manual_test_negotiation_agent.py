"""Standalone (non-pytest) manual check of the full real pipeline:
Contract Analyst -> policy_gate -> Legal/Risk + Business/Finance ->
Negotiation Agent -> grounding_check -> Red-Team, all live API calls
against the same sample contract used by the other manual tests. Run:

    python tests/manual_test_negotiation_agent.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents.business_finance import review_business_finance  # noqa: E402
from agents.contract_analyst import extract_clauses  # noqa: E402
from agents.legal_risk import review_legal_risk  # noqa: E402
from agents.negotiation import negotiate  # noqa: E402
from agents.red_team import review_red_team  # noqa: E402
from harness import load_policy_config, run_policy_check  # noqa: E402
from harness.grounding_check import GroundingStatus, check_grounding  # noqa: E402
from manual_test_contract_analyst import SAMPLE_CONTRACT  # noqa: E402


def main() -> int:
    print("Step 1: Contract Analyst...")
    clauses = extract_clauses(SAMPLE_CONTRACT)
    print(f"  {len(clauses)} clause(s) extracted.\n")

    print("Step 2: Policy check...")
    policy = load_policy_config()
    results = run_policy_check(clauses, policy)
    for r in results:
        print(f"  {r.clause_type}: {r.status.value}")
    print()

    print("Step 3: Legal/Risk Agent...")
    legal_review = review_legal_risk(clauses, results)
    print(f"  verdict={legal_review.verdict.value} confidence={legal_review.confidence}")
    print()

    print("Step 4: Business/Finance Agent...")
    business_review = review_business_finance(clauses, results)
    print(f"  verdict={business_review.verdict.value} confidence={business_review.confidence}")
    print()

    print("Step 5: Negotiation Agent...")
    proposal = negotiate(clauses, results, legal_review, business_review)
    print(proposal.model_dump_json(indent=2))
    print()

    print("Step 6: Grounding check (re-run explicitly for visibility)...")
    grounding = check_grounding(proposal, clauses)
    print(grounding.model_dump_json(indent=2))

    if grounding.status != GroundingStatus.PASSED:
        print("\n*** GROUNDING CHECK FAILED - see above ***")
        return 1
    print("\nGrounding check passed.\n")

    print("Step 7: Red-Team Agent...")
    red_team_review = review_red_team(proposal, clauses, results, legal_review, business_review)
    print(red_team_review.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
