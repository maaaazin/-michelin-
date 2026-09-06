import streamlit as st

st.set_page_config(
    page_title="Warden | Vendor Contract Negotiation",
    page_icon="⚖️",
    layout="wide",
)

st.title("⚖️ Warden")
st.markdown("AI-powered vendor contract negotiation with deterministic policy bounds.")

# State initialization
if "contract_file" not in st.session_state:
    st.session_state.contract_file = None
if "playbook_file" not in st.session_state:
    st.session_state.playbook_file = None

with st.expander("⚙️ Configuration & Uploads", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("1. Vendor Contract")
        contract = st.file_uploader("Upload Contract (.pdf, .docx)", type=["pdf", "docx"])
        if contract:
            st.session_state.contract_file = contract

    with col2:
        st.subheader("2. Company Policy")
        playbook = st.file_uploader("Upload Playbook (.json, .docx, .pdf)", type=["json", "docx", "pdf"])
        if playbook:
            st.session_state.playbook_file = playbook

st.divider()

if not st.session_state.contract_file or not st.session_state.playbook_file:
    st.info("👈 Please upload both a contract and a policy playbook to begin analysis.")
else:
    # Top Metrics Row Placeholder
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Risk Level", "Pending")
    m2.metric("Clauses Extracted", "-")
    m3.metric("Policy Violations", "-")
    m4.metric("Confidence Score", "-")

    # Tabs
    tab1, tab2, tab3 = st.tabs(["📄 Contract Extraction", "🛑 Policy Gate", "🤝 Negotiation Strategy"])

    with tab1:
        st.write("Extraction results will appear here.")
    
    with tab2:
        st.write("Policy Gate evaluation results will appear here.")
        
    with tab3:
        st.write("Agent reviews and negotiation proposal will appear here.")
