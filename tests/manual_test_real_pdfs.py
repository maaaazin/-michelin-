"""Standalone (non-pytest) manual check of the REAL LangGraph-orchestrated
pipeline against the actual demo PDFs in test_docs/ - the first script to
exercise harness.graph.run_negotiation() against real PDF text rather than
a hardcoded sample string. Requires OPENAI_API_KEY in .env; makes real
OpenAI calls for all 5 PDFs. Run:

    python tests/manual_test_real_pdfs.py

Four of the five PDFs (happy_path_demo, failure_demo_policyViolation,
contradictory_contract_demo, hidden_risk_demo) are vendor contracts, each
run against the default data/policy_config.json - the same call app/main.py
makes when no policy PDF is uploaded.

"playbook (1).pdf" is Apex Manufacturing's own vendor-negotiation playbook
(a company policy document, not a contract) - it has no contract of its own
to negotiate over, so it is applied the same way a user would in the
Streamlit app: extract a PolicyConfig from it via agents.policy_analyst
.extract_policy() (exactly app/main.py's "Extract policy from document"
button), then run the graph with that extracted policy against
happy_path_demo.pdf's contract text - the same run_negotiation(policy=...)
call app/main.py makes after a user confirms an extracted policy.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.policy_analyst import extract_policy  # noqa: E402
from harness.graph import run_negotiation  # noqa: E402
from harness.pdf_extraction import extract_text_from_pdf  # noqa: E402
from harness.policy_gate import load_policy_config, run_policy_check  # noqa: E402
from schemas import CheckStatus, NegotiationStage, PolicyConfig, PolicyRuleSource  # noqa: E402

TEST_DOCS = Path(__file__).resolve().parent.parent / "test_docs"

VENDOR_CONTRACTS = [
    "happy_path_demo.pdf",
    "failure_demo_policyViolation.pdf",
    "contradictory_contract_demo.pdf",
    "hidden_risk_demo.pdf",
]
POLICY_DOC = "playbook (1).pdf"
POLICY_DOC_PAIRED_CONTRACT = "happy_path_demo.pdf"


def _print_audit_trail(final_state) -> None:
    print("=== AUDIT TRAIL ===")
    for entry in final_state.negotiation_history:
        print(f"  {entry['event']}")


def _print_unresolved(final_state) -> None:
    """For a HUMAN_REVIEW outcome: which rule(s) are still unresolved and why."""
    results = run_policy_check(final_state.extracted_clauses, final_state.constraints, proposal=final_state.current_offer)
    unresolved = [r for r in results if r.status in (CheckStatus.BLOCKED, CheckStatus.CONFLICTING)]
    if not unresolved:
        print("  (no BLOCKED/CONFLICTING rule at the final proposal - escalation was red-team-driven)")
        return
    for r in unresolved:
        print(f"  - {r.clause_type} [{r.status.value}]: {r.reason}")


def _report(label: str, final_state) -> None:
    _print_audit_trail(final_state)
    print()
    print(f"Final state: {final_state.current_state.value}")
    print(f"Replan attempts used: {final_state.replan_count} / 3")
    if final_state.current_state == NegotiationStage.HUMAN_REVIEW:
        print("Unresolved at escalation:")
        _print_unresolved(final_state)


def run_vendor_contract(filename: str) -> None:
    print(f"\n{'=' * 20} {filename}  (vendor contract, default policy) {'=' * 20}")
    contract_text = extract_text_from_pdf(TEST_DOCS / filename)
    final_state = run_negotiation(
        contract_text,
        negotiation_id=f"NG-{filename}",
        contract_id=f"CTR-{filename}",
    )
    _report(filename, final_state)


def run_policy_doc(filename: str, paired_contract: str) -> None:
    print(f"\n{'=' * 20} {filename}  (company policy doc, applied to {paired_contract}) {'=' * 20}")
    policy_text = extract_text_from_pdf(TEST_DOCS / filename)
    extracted_policy: PolicyConfig = extract_policy(policy_text, default_config=load_policy_config())

    extracted = [r.clause_type for r in extracted_policy.rules if r.source == PolicyRuleSource.EXTRACTED]
    fallback = [r.clause_type for r in extracted_policy.rules if r.source == PolicyRuleSource.DEFAULT_FALLBACK]
    print(f"Policy extraction: {len(extracted)} rule(s) extracted from document, {len(fallback)} fell back to default.")
    if extracted:
        print(f"  Extracted: {', '.join(extracted)}")
    if fallback:
        print(f"  Default fallback: {', '.join(fallback)}")

    contract_text = extract_text_from_pdf(TEST_DOCS / paired_contract)
    final_state = run_negotiation(
        contract_text,
        negotiation_id=f"NG-{filename}",
        contract_id=f"CTR-{paired_contract}",
        policy=extracted_policy,
    )
    _report(filename, final_state)


def main() -> int:
    results: dict[str, str] = {}

    for filename in VENDOR_CONTRACTS:
        try:
            run_vendor_contract(filename)
            results[filename] = "ran"
        except Exception as e:  # noqa: BLE001 - report, don't let one PDF crash the rest
            results[filename] = f"CRASHED: {e}"
            print(f"\n*** {filename} CRASHED ***")
            traceback.print_exc()

    try:
        run_policy_doc(POLICY_DOC, POLICY_DOC_PAIRED_CONTRACT)
        results[POLICY_DOC] = "ran"
    except Exception as e:  # noqa: BLE001
        results[POLICY_DOC] = f"CRASHED: {e}"
        print(f"\n*** {POLICY_DOC} CRASHED ***")
        traceback.print_exc()

    print(f"\n{'=' * 20} SUMMARY {'=' * 20}")
    for filename, outcome in results.items():
        print(f"  {filename}: {outcome}")

    return 0 if all(v == "ran" for v in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
