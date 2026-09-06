"""Standalone (non-pytest) manual check of the Legal/Risk and
Business/Finance review agents against a real OpenAI call. Reuses the
same sample contract as the Contract Analyst manual test, running the
real Contract Analyst + policy_gate first to get real inputs. Run:

    python tests/manual_test_review_agents.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents.business_finance import review_business_finance  # noqa: E402
from agents.contract_analyst import extract_clauses  # noqa: E402
from agents.legal_risk import review_legal_risk  # noqa: E402
from harness import load_policy_config, run_policy_check  # noqa: E402
from manual_test_contract_analyst import SAMPLE_CONTRACT  # noqa: E402


def main() -> int:
    print("Extracting clauses...")
    clauses = extract_clauses(SAMPLE_CONTRACT)
    print(f"  {len(clauses)} clause(s) extracted.\n")

    policy = load_policy_config()
    results = run_policy_check(clauses, policy)
    print("Policy check results:")
    for r in results:
        print(f"  {r.clause_type}: {r.status.value} - {r.reason}")
    print()

    print("Calling Legal/Risk Agent...")
    legal_review = review_legal_risk(clauses, results)
    print(legal_review.model_dump_json(indent=2))
    print("-" * 60)

    print("Calling Business/Finance Agent...")
    business_review = review_business_finance(clauses, results)
    print(business_review.model_dump_json(indent=2))
    print("-" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
