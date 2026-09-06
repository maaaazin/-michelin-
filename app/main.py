import streamlit as st
import json
import pandas as pd
from pathlib import Path
import tempfile
import sys

# Add project root to sys.path so we can import harness and agents
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Backend imports
from harness.pdf_extraction import extract_text_from_pdf
from harness.policy_gate import PolicyConfig, run_policy_check
from agents.contract_analyst import extract_clauses
from agents.legal_risk import review_legal_risk
from agents.business_finance import review_business_finance
from agents.negotiation import negotiate
from schemas import CheckStatus

st.set_page_config(
    page_title="WinWin | Vendor Contract Negotiation",
    page_icon="⚖️",
    layout="wide",
)

# Load CSS
css_path = Path(__file__).parent / "style.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

st.title("⚖️ WinWin")
st.markdown("Automated vendor contract negotiation with deterministic policy bounds.")

# State initialization
if "contract_file" not in st.session_state:
    st.session_state.contract_file = None
if "playbook_file" not in st.session_state:
    st.session_state.playbook_file = None
if "pipeline_run" not in st.session_state:
    st.session_state.pipeline_run = False
if "results" not in st.session_state:
    st.session_state.results = {}

with st.expander("⚙️ Configuration & Uploads", expanded=not st.session_state.pipeline_run):
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("1. Vendor Contract")
        contract = st.file_uploader("Upload Contract (.pdf only)", type=["pdf"])
        if contract:
            st.session_state.contract_file = contract

    with col2:
        st.subheader("2. Company Policy")
        playbook = st.file_uploader("Upload Playbook (.json only)", type=["json"])
        if playbook:
            st.session_state.playbook_file = playbook

st.divider()

if not st.session_state.contract_file or not st.session_state.playbook_file:
    st.info("👈 Please upload both a PDF contract and a JSON policy playbook to begin analysis.")
else:
    # Run Analysis Button
    if st.button("Run Analysis", type="primary", use_container_width=True):
        st.session_state.pipeline_run = True
        
        with st.status("Running WinWin Pipeline...", expanded=True) as status:
            try:
                # 1. Parse Playbook
                st.write("Parsing company policy...")
                policy_dict = json.load(st.session_state.playbook_file)
                policy_config = PolicyConfig.model_validate(policy_dict)
                
                # 2. Extract Text
                st.write("Extracting text from contract PDF...")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(st.session_state.contract_file.getvalue())
                    tmp_path = tmp.name
                contract_text = extract_text_from_pdf(tmp_path)
                
                # 3. Contract Analyst
                st.write("Agent: Contract Analyst extracting clauses...")
                clauses = extract_clauses(contract_text)
                st.session_state.results['clauses'] = clauses
                
                # 4. Policy Gate
                st.write("Harness: Running deterministic policy gate...")
                policy_results = run_policy_check(clauses, policy_config)
                st.session_state.results['policy_results'] = policy_results
                
                # 5. Reviews
                st.write("Agent: Legal/Risk and Business/Finance reviewing...")
                legal_review = review_legal_risk(clauses, policy_results)
                business_review = review_business_finance(clauses, policy_results)
                st.session_state.results['legal_review'] = legal_review
                st.session_state.results['business_review'] = business_review
                
                # 6. Negotiation
                st.write("Agent: Generating negotiation strategy...")
                proposal = negotiate(clauses, policy_results, legal_review, business_review)
                st.session_state.results['proposal'] = proposal
                
                status.update(label="Pipeline complete!", state="complete", expanded=False)
            except Exception as e:
                status.update(label=f"Pipeline failed: {e}", state="error")
                st.error(str(e))
                st.stop()
                
    if st.session_state.pipeline_run and 'clauses' in st.session_state.results:
        res = st.session_state.results
        clauses = res['clauses']
        policy_results = res['policy_results']
        legal_review = res['legal_review']
        business_review = res['business_review']
        proposal = res['proposal']
        
        # Calculate Metrics
        num_clauses = len(clauses)
        avg_confidence = sum(c.confidence for c in clauses) / num_clauses if num_clauses > 0 else 0.0
        num_violations = sum(1 for pr in policy_results if pr.status == CheckStatus.BLOCKED)
        
        risk_level = "LOW"
        if num_violations > 0 or legal_review.verdict.value == "REJECT" or business_review.verdict.value == "REJECT":
            risk_level = "HIGH"
        elif legal_review.verdict.value == "FLAG" or business_review.verdict.value == "FLAG":
            risk_level = "MEDIUM"

        # Top Metrics Row
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Risk Level", risk_level, delta="Requires Attention" if risk_level != "LOW" else "All Clear", delta_color="inverse")
        m2.metric("Clauses Extracted", num_clauses)
        m3.metric("Policy Violations", num_violations, delta=f"{num_violations} Blocked" if num_violations > 0 else "0", delta_color="inverse")
        
        conf_str = f"{avg_confidence*100:.1f}%"
        conf_delta = "Warning: Low Confidence" if avg_confidence < 0.6 else "High Confidence"
        conf_color = "inverse" if avg_confidence < 0.6 else "normal"
        m4.metric("Avg Extraction Confidence", conf_str, delta=conf_delta, delta_color=conf_color)

        # Tabs
        tab1, tab2, tab3 = st.tabs(["📄 Contract Extraction", "🛑 Policy Gate", "🤝 Negotiation Strategy"])

        with tab1:
            st.subheader("Extracted Clauses")
            clause_data = []
            for c in clauses:
                clause_data.append({
                    "Type": c.clause_type,
                    "Value": str(c.vendor_value) if not c.not_specified else "Not Specified",
                    "Unit": c.unit or "-",
                    "Section": c.source_section or "-",
                    "Confidence": f"{c.confidence:.2f}"
                })
            st.dataframe(pd.DataFrame(clause_data), use_container_width=True)
        
        with tab2:
            st.subheader("Policy Evaluation")
            for pr in policy_results:
                if pr.status == CheckStatus.PASS:
                    st.success(f"**{pr.clause_type}**: {pr.reason}")
                elif pr.status == CheckStatus.BLOCKED:
                    st.error(f"**{pr.clause_type}**: {pr.reason}")
                else:
                    st.warning(f"**{pr.clause_type}**: {pr.reason}")
            
        with tab3:
            st.subheader("Negotiation Proposal")
            st.write(f"**Rationale:** {proposal.rationale}")
            
            c_cols = st.columns(2)
            with c_cols[0]:
                st.markdown("#### Concessions")
                if proposal.concessions:
                    for k, v in proposal.concessions.items():
                        st.write(f"- **{k}**: {v}")
                else:
                    st.write("None proposed.")
            with c_cols[1]:
                st.markdown("#### Requested Changes")
                if proposal.requested_changes:
                    for k, v in proposal.requested_changes.items():
                        st.write(f"- **{k}**: {v}")
                else:
                    st.write("None requested.")
            
            st.divider()
            st.subheader("Agent Reviews")
            l_col, b_col = st.columns(2)
            with l_col:
                st.info(f"**Legal/Risk Agent ({legal_review.verdict.value}):**\n\n{legal_review.reasoning}")
            with b_col:
                st.info(f"**Business/Finance Agent ({business_review.verdict.value}):**\n\n{business_review.reasoning}")
