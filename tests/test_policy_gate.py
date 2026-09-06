"""Unit tests for the deterministic policy engine (harness/policy_gate.py).

Covers, at minimum, the cases the harness must get right per
architecture.md / failures.md:
  - a clean pass
  - a hard-limit violation (the 8% vs 5% escalation example)
  - a NOT_SPECIFIED clause
  - a LOW_CONFIDENCE clause
  - the contradiction tie-break (Section 4.2 vs Appendix B, 5% vs 15%)
Plus a couple of extra cases (dynamic reference resolution for
liability_cap, and a proposal overriding the raw vendor value) that
exercise design decisions specific to this implementation.
"""

from pathlib import Path

from schemas import (
    CheckStatus,
    Clause,
    ComparisonDirection,
    NegotiationProposal,
    PolicyConfig,
    PolicyRule,
)
from harness.policy_gate import (
    CONFIDENCE_THRESHOLD,
    evaluate_rule,
    load_policy_config,
    parse_duration_days,
    run_policy_check,
)

ESCALATION_RULE = PolicyRule(
    clause_type="price_escalation",
    target_value=3,
    hard_limit_value=5,
    direction=ComparisonDirection.MAX,
    expected_unit="percent",
    description="Annual price escalation must not exceed 5%.",
)

SLA_RULE = PolicyRule(
    clause_type="sla_uptime",
    target_value=99.9,
    hard_limit_value=99.9,
    direction=ComparisonDirection.MIN,
    expected_unit="percent",
    description="SLA uptime must be at least 99.9%.",
)

DATA_OWNERSHIP_RULE = PolicyRule(
    clause_type="data_ownership",
    target_value="company",
    hard_limit_value="company",
    direction=ComparisonDirection.EQUALS,
    description="Data must remain owned by the company.",
)

PAYMENT_TERMS_RULE = PolicyRule(
    clause_type="payment_terms_days",
    target_value=60,
    hard_limit_value=30,
    direction=ComparisonDirection.MIN,
    expected_unit="days",
    description="Payment terms must be at least Net 30.",
)

TERMINATION_RULE = PolicyRule(
    clause_type="termination_notice_days",
    target_value=30,
    hard_limit_value=60,
    direction=ComparisonDirection.MAX,
    expected_unit="days",
    description="Termination notice must not exceed 60 days.",
)

LIABILITY_RULE = PolicyRule(
    clause_type="liability_cap",
    target_value="annual_contract_value",
    hard_limit_value="annual_contract_value",
    direction=ComparisonDirection.MIN,
    description="Liability cap must be at least the annual contract value.",
    reference_clause_type="annual_contract_value",
)


def test_clean_pass_within_policy():
    clause = Clause(
        clause_type="price_escalation",
        vendor_value=4,
        unit="percent",
        source_section="4.1",
        source_text="Annual fees may increase by up to 4%.",
        confidence=0.95,
    )
    result = evaluate_rule(ESCALATION_RULE, [clause])
    assert result.status == CheckStatus.PASS
    assert result.checked_value == 4
    assert result.hard_limit_value == 5


def test_hard_limit_violation_8_percent_vs_5_percent_max():
    clause = Clause(
        clause_type="price_escalation",
        vendor_value=8,
        unit="percent",
        source_section="4.2",
        source_text="Annual fees may increase by 8%.",
        confidence=0.96,
    )
    result = evaluate_rule(ESCALATION_RULE, [clause])
    assert result.status == CheckStatus.BLOCKED
    assert result.checked_value == 8
    assert result.hard_limit_value == 5
    assert "exceeds" in result.reason


def test_not_specified_clause_is_cannot_verify_not_pass_or_fail():
    clause = Clause(
        clause_type="data_ownership",
        not_specified=True,
        confidence=0.9,
    )
    result = evaluate_rule(DATA_OWNERSHIP_RULE, [clause])
    assert result.status == CheckStatus.CANNOT_VERIFY
    assert result.checked_value is None


def test_missing_clause_entirely_is_also_cannot_verify():
    # No Clause at all for this clause_type - same treatment as an
    # explicit NOT_SPECIFIED marker.
    result = evaluate_rule(SLA_RULE, [])
    assert result.status == CheckStatus.CANNOT_VERIFY


def test_low_confidence_clause_is_blocked_from_use_as_fact():
    clause = Clause(
        clause_type="sla_uptime",
        vendor_value=99.5,
        unit="percent",
        source_section="8.1",
        source_text="Vendor guarantees roughly 99.5% uptime, terms unclear.",
        confidence=0.4,  # below CONFIDENCE_THRESHOLD
    )
    assert clause.confidence < CONFIDENCE_THRESHOLD
    result = evaluate_rule(SLA_RULE, [clause])
    # Must NOT be silently treated as BLOCKED (99.5 < 99.9 would fail the
    # hard-limit check) - low confidence takes precedence over PASS/BLOCKED.
    assert result.status == CheckStatus.LOW_CONFIDENCE
    assert result.checked_value is None


def test_contradiction_tie_break_section_4_2_vs_appendix_b():
    section_4_2 = Clause(
        clause_type="price_escalation",
        vendor_value=5,
        unit="percent",
        source_section="4.2",
        source_text="Annual escalation shall not exceed 5%.",
        confidence=0.95,
    )
    appendix_b = Clause(
        clause_type="price_escalation",
        vendor_value=15,
        unit="percent",
        source_section="Appendix B",
        source_text="Vendor may increase fees by up to 15% at renewal.",
        confidence=0.9,
    )
    result = evaluate_rule(ESCALATION_RULE, [section_4_2, appendix_b])

    assert result.status == CheckStatus.CONFLICTING
    assert result.requires_human_signoff is True
    # Tie-break: MAX direction -> take the more conservative (lower) value.
    assert result.checked_value == 5
    assert "4.2" in result.reason
    assert "Appendix B" in result.reason
    assert "5" in result.reason and "15" in result.reason


def test_contradiction_tie_break_min_direction_takes_higher_value():
    # For a MIN-direction rule (higher is better for the company), the
    # more company-favorable resolution is the larger of the two values.
    low = Clause(
        clause_type="sla_uptime",
        vendor_value=99.5,
        source_section="8.1",
        source_text="...99.5%...",
        confidence=0.9,
    )
    high = Clause(
        clause_type="sla_uptime",
        vendor_value=99.9,
        source_section="Schedule C",
        source_text="...99.9%...",
        confidence=0.9,
    )
    result = evaluate_rule(SLA_RULE, [low, high])
    assert result.status == CheckStatus.CONFLICTING
    assert result.checked_value == 99.9


def test_liability_cap_resolves_dynamic_reference_and_blocks():
    annual_value = Clause(
        clause_type="annual_contract_value",
        vendor_value=2_000_000,
        unit="INR",
        source_section="1.1",
        source_text="Total annual contract value: Rs 20,00,000.",
        confidence=0.98,
    )
    liability = Clause(
        clause_type="liability_cap",
        vendor_value=200_000,
        unit="INR",
        source_section="9.3",
        source_text="Vendor's total liability shall not exceed Rs 2,00,000.",
        confidence=0.93,
    )
    result = evaluate_rule(LIABILITY_RULE, [annual_value, liability])
    assert result.status == CheckStatus.BLOCKED
    assert result.hard_limit_value == 2_000_000
    assert result.checked_value == 200_000


def test_liability_cap_cannot_verify_when_reference_missing():
    liability = Clause(
        clause_type="liability_cap",
        vendor_value=200_000,
        source_section="9.3",
        source_text="Vendor's total liability shall not exceed Rs 2,00,000.",
        confidence=0.93,
    )
    result = evaluate_rule(LIABILITY_RULE, [liability])
    assert result.status == CheckStatus.CANNOT_VERIFY


def test_proposal_overrides_vendor_value_for_the_gate_check():
    # POLICY_GATE usage: the underlying vendor evidence is out of policy,
    # but the negotiation agent's proposal brings it into compliance.
    vendor_clause = Clause(
        clause_type="price_escalation",
        vendor_value=8,
        unit="percent",
        source_section="4.2",
        source_text="Annual fees may increase by 8%.",
        confidence=0.96,
    )
    proposal = NegotiationProposal(
        concessions={"price_escalation": 5},
        rationale="Counter-offer at the company's hard maximum.",
        supporting_clauses=[],
    )
    result = evaluate_rule(ESCALATION_RULE, [vendor_clause], proposal=proposal)
    assert result.status == CheckStatus.PASS
    assert result.checked_value == 5


def test_run_policy_check_returns_one_result_per_rule():
    policy = PolicyConfig(rules=[ESCALATION_RULE, SLA_RULE])
    clauses = [
        Clause(
            clause_type="price_escalation",
            vendor_value=4,
            source_section="4.1",
            source_text="...4%...",
            confidence=0.9,
        ),
    ]
    results = run_policy_check(clauses, policy)
    assert len(results) == 2
    statuses = {r.clause_type: r.status for r in results}
    assert statuses["price_escalation"] == CheckStatus.PASS
    assert statuses["sla_uptime"] == CheckStatus.CANNOT_VERIFY


def test_load_policy_config_from_data_file():
    policy = load_policy_config()
    assert isinstance(policy, PolicyConfig)
    clause_types = {rule.clause_type for rule in policy.rules}
    assert clause_types == {
        "price_escalation",
        "payment_terms_days",
        "termination_notice_days",
        "liability_cap",
        "sla_uptime",
        "data_ownership",
        "auto_renewal_cancellation_window_days",
    }


def test_data_file_actually_exists():
    assert (Path(__file__).resolve().parent.parent / "data" / "policy_config.json").exists()


# --- Value normalization: the three comparison strategies (task step 2) ---


def test_numeric_strategy_checks_unit_not_just_magnitude():
    # Same magnitude as a passing case, but the unit is wrong for a
    # percent-type rule - must not be silently compared as if correct.
    clause = Clause(
        clause_type="price_escalation",
        vendor_value=4,
        unit="INR",
        source_section="4.1",
        source_text="...4...",
        confidence=0.9,
    )
    result = evaluate_rule(ESCALATION_RULE, [clause])
    assert result.status == CheckStatus.CANNOT_VERIFY
    assert "unit mismatch" in result.reason.lower()


def test_duration_strategy_parses_net_terms_and_passes():
    clause = Clause(
        clause_type="payment_terms_days",
        vendor_value="Net 45",
        source_section="6.1",
        source_text="Payment due Net 45.",
        confidence=0.92,
    )
    result = evaluate_rule(PAYMENT_TERMS_RULE, [clause])
    assert result.status == CheckStatus.PASS
    assert result.checked_value == 45


def test_duration_strategy_parses_days_suffix_and_blocks():
    clause = Clause(
        clause_type="termination_notice_days",
        vendor_value="180 days",
        source_section="12.1",
        source_text="Either party may terminate with 180 days notice.",
        confidence=0.95,
    )
    result = evaluate_rule(TERMINATION_RULE, [clause])
    assert result.status == CheckStatus.BLOCKED
    assert result.checked_value == 180


def test_duration_strategy_malformed_string_is_cannot_verify_not_a_crash():
    clause = Clause(
        clause_type="payment_terms_days",
        vendor_value="due upon receipt, terms TBD",
        source_section="6.1",
        source_text="Payment terms to be determined.",
        confidence=0.8,
    )
    result = evaluate_rule(PAYMENT_TERMS_RULE, [clause])
    assert result.status == CheckStatus.CANNOT_VERIFY
    assert parse_duration_days("due upon receipt, terms TBD") is None


def test_categorical_strategy_pass_and_blocked():
    matching = Clause(
        clause_type="data_ownership",
        vendor_value="Company",
        source_section="10.1",
        source_text="All data remains the property of the Company.",
        confidence=0.9,
    )
    assert evaluate_rule(DATA_OWNERSHIP_RULE, [matching]).status == CheckStatus.PASS

    mismatched = Clause(
        clause_type="data_ownership",
        vendor_value="Vendor",
        source_section="10.1",
        source_text="All data remains the property of the Vendor.",
        confidence=0.9,
    )
    assert evaluate_rule(DATA_OWNERSHIP_RULE, [mismatched]).status == CheckStatus.BLOCKED
