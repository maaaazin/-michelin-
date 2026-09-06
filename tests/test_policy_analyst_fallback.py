"""Unit tests for the Policy Analyst's fallback logic
(agents/policy_analyst._build_policy_config). No live API call needed -
this exercises the merge/fallback logic directly against a stubbed
extraction result, per the module's design (see its docstring).
"""

from harness.policy_gate import load_policy_config
from schemas import PolicyRuleSource
from agents.policy_analyst import (
    POLICY_RULE_CONFIDENCE_THRESHOLD,
    _ExtractedRuleConfidence,
    _build_policy_config,
)

DEFAULT_CONFIG = load_policy_config()
DEFAULTS_BY_TYPE = {r.clause_type: r for r in DEFAULT_CONFIG.rules}


def _rule(new_config, clause_type):
    return next(r for r in new_config.rules if r.clause_type == clause_type)


def test_high_confidence_numeric_rule_is_extracted():
    extracted = {
        "price_escalation": _ExtractedRuleConfidence(
            clause_type="price_escalation", found=True, confidence=0.95, target_value=2, hard_limit_value=4
        )
    }
    result = _build_policy_config(DEFAULT_CONFIG, DEFAULTS_BY_TYPE, extracted)
    rule = _rule(result, "price_escalation")
    assert rule.source == PolicyRuleSource.EXTRACTED
    assert rule.target_value == 2
    assert rule.hard_limit_value == 4
    assert rule.confidence == 0.95


def test_low_confidence_rule_falls_back_to_default():
    default_rule = DEFAULTS_BY_TYPE["price_escalation"]
    extracted = {
        "price_escalation": _ExtractedRuleConfidence(
            clause_type="price_escalation",
            found=True,
            confidence=POLICY_RULE_CONFIDENCE_THRESHOLD - 0.1,
            target_value=2,
            hard_limit_value=4,
        )
    }
    result = _build_policy_config(DEFAULT_CONFIG, DEFAULTS_BY_TYPE, extracted)
    rule = _rule(result, "price_escalation")
    assert rule.source == PolicyRuleSource.DEFAULT_FALLBACK
    assert rule.target_value == default_rule.target_value
    assert rule.hard_limit_value == default_rule.hard_limit_value
    assert rule.confidence == 1.0


def test_rule_missing_from_extraction_falls_back_to_default():
    # sla_uptime never appears in the extracted dict at all.
    default_rule = DEFAULTS_BY_TYPE["sla_uptime"]
    result = _build_policy_config(DEFAULT_CONFIG, DEFAULTS_BY_TYPE, extracted_by_type={})
    rule = _rule(result, "sla_uptime")
    assert rule.source == PolicyRuleSource.DEFAULT_FALLBACK
    assert rule.target_value == default_rule.target_value
    assert rule.hard_limit_value == default_rule.hard_limit_value


def test_not_found_rule_falls_back_even_with_high_confidence():
    # found=False must win regardless of the confidence value.
    extracted = {
        "termination_notice_days": _ExtractedRuleConfidence(
            clause_type="termination_notice_days", found=False, confidence=0.99, target_value=10, hard_limit_value=20
        )
    }
    result = _build_policy_config(DEFAULT_CONFIG, DEFAULTS_BY_TYPE, extracted)
    rule = _rule(result, "termination_notice_days")
    assert rule.source == PolicyRuleSource.DEFAULT_FALLBACK


def test_categorical_rule_extracted_keeps_template_value():
    # data_ownership has no meaningful number - a confident "found" uses
    # the template's own target/hard_limit_value, just tagged extracted.
    default_rule = DEFAULTS_BY_TYPE["data_ownership"]
    extracted = {
        "data_ownership": _ExtractedRuleConfidence(clause_type="data_ownership", found=True, confidence=0.9)
    }
    result = _build_policy_config(DEFAULT_CONFIG, DEFAULTS_BY_TYPE, extracted)
    rule = _rule(result, "data_ownership")
    assert rule.source == PolicyRuleSource.EXTRACTED
    assert rule.target_value == default_rule.target_value
    assert rule.hard_limit_value == default_rule.hard_limit_value


def test_numeric_rule_missing_values_despite_high_confidence_falls_back():
    # A malformed extraction (found + high confidence but no numbers at
    # all) must not be treated as usable just because confidence looks fine.
    extracted = {
        "sla_uptime": _ExtractedRuleConfidence(clause_type="sla_uptime", found=True, confidence=0.9)
    }
    result = _build_policy_config(DEFAULT_CONFIG, DEFAULTS_BY_TYPE, extracted)
    rule = _rule(result, "sla_uptime")
    assert rule.source == PolicyRuleSource.DEFAULT_FALLBACK


def test_numeric_rule_with_only_one_value_given_uses_it_for_both():
    # A document stating one threshold ("at least 99.9% uptime") with no
    # separate target vs hard limit is still a usable, confident extraction.
    extracted = {
        "sla_uptime": _ExtractedRuleConfidence(
            clause_type="sla_uptime", found=True, confidence=0.9, target_value=99.9, hard_limit_value=None
        )
    }
    result = _build_policy_config(DEFAULT_CONFIG, DEFAULTS_BY_TYPE, extracted)
    rule = _rule(result, "sla_uptime")
    assert rule.source == PolicyRuleSource.EXTRACTED
    assert rule.target_value == 99.9
    assert rule.hard_limit_value == 99.9
