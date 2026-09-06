import streamlit as st
import pandas as pd
from pathlib import Path
import tempfile
import sys

# Add project root to sys.path so we can import harness and agents
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Backend imports
from harness.pdf_extraction import extract_text_from_pdf
from harness.policy_gate import load_policy_config, run_policy_check
from harness.graph import run_negotiation
from agents.policy_analyst import extract_policy
from schemas import CheckStatus, NegotiationStage, PolicyRuleSource

st.set_page_config(
    page_title="Warden | Vendor Contract Negotiation",
    page_icon="⚖️",
    layout="wide",
)

# Load CSS
css_path = Path(__file__).parent / "style.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

st.title("⚖️ Warden")
st.markdown(
    "Warden lets AI negotiate vendor contracts, but puts every AI-generated "
    "negotiation move through an enforceable policy, evidence, and "
    "independent-review harness before allowing it to proceed."
)

# --- Session state ---
for key, default in {
    "contract_file": None,
    "policy_file": None,
    "extracted_policy": None,
    "policy_confirmed": False,
    "final_state": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


def _pdf_text(uploaded_file) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name
    return extract_text_from_pdf(tmp_path)


# --- Uploads ---
with st.expander("⚙️ Uploads", expanded=st.session_state.final_state is None):
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("1. Vendor Contract (required)")
        contract = st.file_uploader("Upload the vendor contract", type=["pdf"], key="contract_uploader")
        if contract is not None:
            st.session_state.contract_file = contract

    with col2:
        st.subheader("2. Company Policy (optional)")
        st.caption("If omitted, Warden uses the default company policy (data/policy_config.json).")
        policy_pdf = st.file_uploader("Upload the company policy document", type=["pdf"], key="policy_uploader")
        if policy_pdf is not None and policy_pdf is not st.session_state.policy_file:
            st.session_state.policy_file = policy_pdf
            st.session_state.extracted_policy = None
            st.session_state.policy_confirmed = False

st.divider()

contract_ready = st.session_state.contract_file is not None

# --- Policy extraction preview (only if a policy PDF was uploaded) ---
if st.session_state.policy_file is not None and st.session_state.extracted_policy is None:
    if st.button("Extract policy from document", type="secondary"):
        with st.spinner("Policy Analyst reading the document..."):
            policy_text = _pdf_text(st.session_state.policy_file)
            st.session_state.extracted_policy = extract_policy(policy_text, default_config=load_policy_config())
        st.rerun()

if st.session_state.extracted_policy is not None and not st.session_state.policy_confirmed:
    st.subheader("📋 Extracted Company Policy — review before running")
    rows = []
    for rule in st.session_state.extracted_policy.rules:
        rows.append(
            {
                "Rule": rule.clause_type,
                "Target": rule.target_value,
                "Hard limit": rule.hard_limit_value,
                "Confidence": f"{rule.confidence:.2f}",
                "Source": "📄 Extracted" if rule.source == PolicyRuleSource.EXTRACTED else "⚙️ Default fallback",
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    fallback_count = sum(
        1 for r in st.session_state.extracted_policy.rules if r.source == PolicyRuleSource.DEFAULT_FALLBACK
    )
    if fallback_count:
        st.warning(f"{fallback_count} rule(s) used the default fallback - not confidently found in the document.")
    if st.button("✅ Confirm and continue with this policy", type="primary"):
        st.session_state.policy_confirmed = True
        st.rerun()
    st.info("Review the extracted policy above and confirm before running the negotiation.")

# --- Run ---
policy_gated = st.session_state.policy_file is not None and not st.session_state.policy_confirmed
can_run = contract_ready and not policy_gated

if not contract_ready:
    st.info("👈 Upload a vendor contract PDF to begin.")
elif policy_gated:
    st.info("👆 Extract and confirm the company policy above before running the negotiation.")
else:
    if st.button("🚀 Run Warden", type="primary", use_container_width=True, disabled=not can_run):
        with st.spinner("Running the Warden pipeline (contract analysis, policy check, reviews, negotiation, red-team, replan loop)..."):
            contract_text = _pdf_text(st.session_state.contract_file)
            effective_policy = st.session_state.extracted_policy or load_policy_config()
            try:
                st.session_state.final_state = run_negotiation(contract_text, policy=effective_policy)
            except Exception as e:
                st.error(f"Pipeline failed: {e}")
                st.session_state.final_state = None

# --- Results ---
final_state = st.session_state.final_state
if final_state is not None:
    st.divider()

    num_clauses = len(final_state.extracted_clauses)
    num_blocked = sum(1 for r in final_state.violations if r.status == CheckStatus.BLOCKED)
    num_conflicting = sum(1 for r in final_state.violations if r.status == CheckStatus.CONFLICTING)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Clauses extracted", num_clauses)
    m2.metric("Policy violations (initial)", num_blocked)
    m3.metric("Conflicts needing sign-off", num_conflicting)
    m4.metric("Replan attempts used", f"{final_state.replan_count} / 3")

    tab1, tab2, tab3 = st.tabs(["📜 Audit Trail", "📄 Extracted Clauses", "🤝 Outcome"])

    with tab1:
        st.subheader("Audit Trail")
        for entry in final_state.negotiation_history:
            st.text(f"• {entry['event']}")

    with tab2:
        st.subheader("Extracted Clauses")
        clause_rows = [
            {
                "Type": c.clause_type,
                "Value": "Not specified" if c.not_specified else str(c.vendor_value),
                "Unit": c.unit or "-",
                "Section": c.source_section or "-",
                "Confidence": f"{c.confidence:.2f}",
            }
            for c in final_state.extracted_clauses
        ]
        st.dataframe(pd.DataFrame(clause_rows), use_container_width=True)

    with tab3:
        st.subheader("Outcome")
        if final_state.current_state == NegotiationStage.FINAL:
            st.success("✅ Final proposal approved.")
            proposal = final_state.current_offer
            if proposal:
                st.write(f"**Rationale:** {proposal.rationale}")
                c_cols = st.columns(2)
                with c_cols[0]:
                    st.markdown("#### Concessions")
                    for k, v in (proposal.concessions or {"None": "-"}).items():
                        st.write(f"- **{k}**: {v}")
                with c_cols[1]:
                    st.markdown("#### Requested Changes")
                    for k, v in (proposal.requested_changes or {"None": "-"}).items():
                        st.write(f"- **{k}**: {v}")
        elif final_state.current_state == NegotiationStage.HUMAN_REVIEW:
            st.error("🛑 Escalated to Human Review — the replan loop could not reach an approvable proposal.")
            final_gate = run_policy_check(
                final_state.extracted_clauses, final_state.constraints, proposal=final_state.current_offer
            )
            unresolved = [r for r in final_gate if r.status in (CheckStatus.BLOCKED, CheckStatus.CONFLICTING)]
            if unresolved:
                st.write("**Still unresolved:**")
                for r in unresolved:
                    st.warning(f"**{r.clause_type}** ({r.status.value}): {r.reason}")
            red_team_reviews = [rv for rv in final_state.agent_reviews if rv.agent_name == "Red-Team Agent"]
            if red_team_reviews and red_team_reviews[-1].verdict.value == "REJECT":
                st.write("**Red-Team's last objection:**")
                st.warning(red_team_reviews[-1].reasoning)
            if final_state.current_offer:
                st.write("**Last proposal attempted:**")
                st.json(final_state.current_offer.model_dump())
        else:
            st.warning(f"Unexpected terminal state: {final_state.current_state.value}")

        st.divider()
        st.subheader("Agent Reviews")
        for review in final_state.agent_reviews:
            if review.agent_name in ("Legal/Risk Agent", "Business/Finance Agent"):
                st.info(f"**{review.agent_name} ({review.verdict.value}):**\n\n{review.reasoning}")
