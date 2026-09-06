import html
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Add project root to sys.path so we can import harness and agents
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Backend imports
from harness.pdf_extraction import extract_text_from_pdf
from harness.policy_gate import load_policy_config, run_policy_check
from harness.graph import run_negotiation
from agents.policy_analyst import extract_policy
from schemas import CheckStatus, NegotiationStage, PolicyRuleSource

st.set_page_config(
    page_title="WinWin | Vendor Contract Negotiation",
    page_icon="⚖",
    layout="wide",
)

# Load CSS
css_path = Path(__file__).parent / "style.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

_STATUS_CLASS = {
    "PASS": "status-pass",
    "ACCEPT": "status-pass",
    "BLOCKED": "status-blocked",
    "REJECT": "status-blocked",
    "CONFLICTING": "status-conflicting",
    "CANNOT_VERIFY": "status-cannot_verify",
    "LOW_CONFIDENCE": "status-low_confidence",
    "FLAG": "status-conflicting",
}


def _badge(value: str) -> str:
    css_class = _STATUS_CLASS.get(value, "status-cannot_verify")
    return f'<span class="status-badge {css_class}">{html.escape(value)}</span>'


st.title("WinWin")
st.markdown(
    '<div class="app-subtitle">WinWin lets AI negotiate vendor contracts, but puts every '
    "AI-generated negotiation move through an enforceable policy, evidence, and "
    "independent-review harness before allowing it to proceed.</div>",
    unsafe_allow_html=True,
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
    # Reads the upload's bytes directly via PyMuPDF's stream API - no
    # temp file, so no Windows-specific file-locking risk from writing
    # then reopening the same path through a second handle.
    return extract_text_from_pdf(uploaded_file.getvalue())


# --- Uploads ---
with st.expander("Uploads", expanded=st.session_state.final_state is None):
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("1. Vendor Contract (required)")
        contract = st.file_uploader("Upload the vendor contract", type=["pdf"], key="contract_uploader")
        if contract is not None:
            st.session_state.contract_file = contract

    with col2:
        st.subheader("2. Company Policy (optional)")
        st.caption("If omitted, WinWin uses the default company policy (data/policy_config.json).")
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
    st.subheader("Extracted Company Policy — review before running")
    rows = []
    for rule in st.session_state.extracted_policy.rules:
        rows.append(
            {
                "Rule": rule.clause_type,
                "Target": rule.target_value,
                "Hard limit": rule.hard_limit_value,
                "Confidence": rule.confidence,
                "Source": "Extracted" if rule.source == PolicyRuleSource.EXTRACTED else "Default fallback",
            }
        )
    policy_df = pd.DataFrame(rows)
    styled_policy = policy_df.style.map(
        lambda v: "color: #1F7A4D;" if v == "Extracted" else "color: #8A93A1;", subset=["Source"]
    ).format({"Confidence": "{:.2f}"})
    st.dataframe(styled_policy, use_container_width=True)
    fallback_count = sum(
        1 for r in st.session_state.extracted_policy.rules if r.source == PolicyRuleSource.DEFAULT_FALLBACK
    )
    if fallback_count:
        st.warning(f"{fallback_count} rule(s) used the default fallback - not confidently found in the document.")
    if st.button("Confirm and continue with this policy", type="primary"):
        st.session_state.policy_confirmed = True
        st.rerun()
    st.info("Review the extracted policy above and confirm before running the negotiation.")

# --- Run ---
policy_gated = st.session_state.policy_file is not None and not st.session_state.policy_confirmed
can_run = contract_ready and not policy_gated

if not contract_ready:
    st.info("Upload a vendor contract PDF to begin.")
elif policy_gated:
    st.info("Extract and confirm the company policy above before running the negotiation.")
else:
    if st.button("Run WinWin", type="primary", use_container_width=True, disabled=not can_run):
        with st.spinner("Running the WinWin pipeline (contract analysis, policy check, reviews, negotiation, red-team, replan loop)..."):
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

    tab1, tab2, tab3 = st.tabs(["Audit Trail", "Extracted Clauses", "Outcome"])

    with tab1:
        st.subheader("Audit Trail")
        lines = "".join(
            f'<div class="audit-line"><span class="audit-index">{i}.</span>'
            f'<span>{html.escape(entry["event"])}</span></div>'
            for i, entry in enumerate(final_state.negotiation_history, start=1)
        )
        st.markdown(f'<div class="audit-log">{lines}</div>', unsafe_allow_html=True)

    with tab2:
        st.subheader("Extracted Clauses")
        clause_rows = [
            {
                "Type": c.clause_type,
                "Value": "Not specified" if c.not_specified else str(c.vendor_value),
                "Unit": c.unit or "-",
                "Section": c.source_section or "-",
                "Confidence": c.confidence,
            }
            for c in final_state.extracted_clauses
        ]
        clause_df = pd.DataFrame(clause_rows)
        styled_clauses = clause_df.style.map(
            lambda v: "color: #1F7A4D; font-weight: 600;" if v >= 0.6 else "color: #A85E00; font-weight: 600;",
            subset=["Confidence"],
        ).format({"Confidence": "{:.2f}"})
        st.dataframe(styled_clauses, use_container_width=True)

    with tab3:
        st.subheader("Outcome")
        if final_state.current_state == NegotiationStage.FINAL:
            st.markdown(
                '<div class="outcome-banner final">'
                '<div class="outcome-title">Final proposal approved</div>'
                '<div class="outcome-detail">Every policy check passed and the Red-Team review accepted the proposal.</div>'
                "</div>",
                unsafe_allow_html=True,
            )
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
            st.markdown(
                '<div class="outcome-banner human-review">'
                '<div class="outcome-title">Escalated to human review</div>'
                '<div class="outcome-detail">The replan loop reached its limit without an approvable proposal. '
                "This is an explicit stop, not a system failure - a person needs to review and decide.</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            final_gate = run_policy_check(
                final_state.extracted_clauses, final_state.constraints, proposal=final_state.current_offer
            )
            unresolved = [r for r in final_gate if r.status in (CheckStatus.BLOCKED, CheckStatus.CONFLICTING)]
            if unresolved:
                st.markdown('<div class="section-label">Still unresolved</div>', unsafe_allow_html=True)
                for r in unresolved:
                    border_class = "conflicting" if r.status == CheckStatus.CONFLICTING else ""
                    st.markdown(
                        f'<div class="unresolved-rule {border_class}">'
                        f'<span class="rule-name">{html.escape(r.clause_type)}</span>{_badge(r.status.value)}'
                        f'<div class="rule-reason">{html.escape(r.reason)}</div>'
                        "</div>",
                        unsafe_allow_html=True,
                    )
            red_team_reviews = [rv for rv in final_state.agent_reviews if rv.agent_name == "Red-Team Agent"]
            if red_team_reviews and red_team_reviews[-1].verdict.value == "REJECT":
                st.markdown('<div class="section-label">Red-Team\'s last objection</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="unresolved-rule">{html.escape(red_team_reviews[-1].reasoning)}</div>',
                    unsafe_allow_html=True,
                )
            if final_state.current_offer:
                with st.expander("Last proposal attempted (raw)"):
                    st.json(final_state.current_offer.model_dump())
        else:
            st.warning(f"Unexpected terminal state: {final_state.current_state.value}")

        st.divider()
        st.subheader("Agent Reviews")
        for review in final_state.agent_reviews:
            if review.agent_name in ("Legal/Risk Agent", "Business/Finance Agent"):
                st.markdown(
                    f'<div class="unresolved-rule"><span class="rule-name">{html.escape(review.agent_name)}</span>'
                    f"{_badge(review.verdict.value)}"
                    f'<div class="rule-reason">{html.escape(review.reasoning)}</div></div>',
                    unsafe_allow_html=True,
                )
