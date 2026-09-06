"""Standalone (non-pytest) manual check of the full LangGraph-orchestrated
negotiation pipeline - the real graph from harness/graph.py, not manually
chained function calls - against the same sample contract used by the
other manual tests. Runs it twice: once with the default
data/policy_config.json (no policy PDF), once with an inline sample
policy text to confirm the POLICY_EXTRACTION step engages correctly.
Prints negotiation_history as the audit trail each time. Run:

    python tests/manual_test_full_graph.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness.graph import run_negotiation  # noqa: E402
from manual_test_contract_analyst import SAMPLE_CONTRACT  # noqa: E402
from manual_test_policy_analyst import SAMPLE_POLICY  # noqa: E402


def run_once(label: str, policy_text: Optional[str] = None) -> bool:
    print(f"\n{'=' * 20} {label} {'=' * 20}")
    final_state = run_negotiation(
        SAMPLE_CONTRACT, negotiation_id="NG-DEMO", contract_id="CTR-DEMO", policy_text=policy_text
    )

    print("=== AUDIT TRAIL ===")
    for entry in final_state.negotiation_history:
        print(f"  {entry['event']}")
    print()

    print(f"Final state: {final_state.current_state.value}")
    print(f"Replan attempts used: {final_state.replan_count} (max 3)")

    replanned = any("Replanning" in entry.get("event", "") for entry in final_state.negotiation_history)
    print(f"Replan loop triggered: {replanned}")

    if final_state.current_state.value not in ("FINAL", "HUMAN_REVIEW"):
        print(f"\n*** UNEXPECTED TERMINAL STATE: {final_state.current_state.value} ***")
        return False
    return True


def main() -> int:
    ok_default = run_once("DEFAULT POLICY (no PDF)")
    ok_extracted = run_once("EXTRACTED POLICY (inline sample text)", policy_text=SAMPLE_POLICY)
    return 0 if (ok_default and ok_extracted) else 1


if __name__ == "__main__":
    raise SystemExit(main())
