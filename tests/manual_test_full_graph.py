"""Standalone (non-pytest) manual check of the full LangGraph-orchestrated
negotiation pipeline - the real graph from harness/graph.py, not manually
chained function calls - against the same sample contract used by the
other manual tests. Prints negotiation_history as the audit trail. Run:

    python tests/manual_test_full_graph.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness.graph import run_negotiation  # noqa: E402
from manual_test_contract_analyst import SAMPLE_CONTRACT  # noqa: E402


def main() -> int:
    final_state = run_negotiation(SAMPLE_CONTRACT, negotiation_id="NG-DEMO", contract_id="CTR-DEMO")

    print("=== AUDIT TRAIL ===")
    for entry in final_state.negotiation_history:
        print(f"  {entry['event']}")
    print()

    print(f"Final state: {final_state.current_state.value}")
    print(f"Replan attempts used: {final_state.replan_count} (max {3})")
    print()

    print("Final proposal:")
    if final_state.current_offer:
        print(final_state.current_offer.model_dump_json(indent=2))
    else:
        print("  (none)")
    print()

    replanned = any("Replanning" in entry.get("event", "") for entry in final_state.negotiation_history)
    print(f"Replan loop triggered: {replanned}")

    if final_state.current_state.value not in ("FINAL", "HUMAN_REVIEW"):
        print(f"\n*** UNEXPECTED TERMINAL STATE: {final_state.current_state.value} ***")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
