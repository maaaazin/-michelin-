# Warden — Failure Modes (why a harness, not a chatbot)

This document lists the specific ways a single-LLM contract-negotiation
workflow fails silently, and the deterministic mechanism in Warden's
harness that is designed to catch each one. If a failure mode here has no
corresponding mechanism, that is a gap to close before calling the core
build done.

The organizing claim: none of these failures require a smarter model to
fix. They require an independent check that does not trust the model to
report on itself.

---

## 1. Policy violations

**What it looks like:** The negotiation agent proposes a term that
breaks a hard company constraint (for example, an 8% escalation against
a 5% hard maximum), often bundled with a plausible-sounding trade-off
that makes it read as reasonable.

**Why an LLM alone will not reliably catch it:** The same model
proposing the trade-off is the one that would have to notice it broke a
rule. Under conversational pressure to sound cooperative or to close a
deal, it can rationalize the violation instead of flagging it.

**Harness mechanism:** The `POLICY_GATE` runs a plain-code comparison
(`proposed_value > hard_max`, etc.) against structured company policy on
every proposed move, with no LLM in that decision. A failing check
routes back to `NEGOTIATION_PLANNING` (replan), not forward.

---

## 2. Unsupported or invented claims

**What it looks like:** The model states a contract term that is not
actually what the source text says (claiming a 99.9% SLA when the
contract says 99.5%), or asserts a fact with no clause backing it at
all.

**Why an LLM alone will not reliably catch it:** Natural-language output
does not distinguish "I am quoting the contract" from "I am inferring or
recalling this." Both come out as the same confident sentence.

**Harness mechanism:** Every fact the Negotiation Agent uses must
reference a `clause_id` in the evidence store, which carries the source
section and exact source text. A claim with no evidence reference, or
one that does not match the cited evidence, is not eligible to be used
in a proposal - evidence grounding is enforced structurally, not by
asking the model to cite its sources and trusting it did so accurately.

---

## 3. Missed contradictions

**What it looks like:** The contract contains two clauses addressing the
same term with different values (Section 4.2 caps escalation at 5%;
Appendix B allows 15% at renewal). A single pass over the document can
read one, miss the other, or blend them into a number neither clause
actually supports.

**Why an LLM alone will not reliably catch it:** Nothing forces a
line-by-line cross-check of every clause against every other clause
addressing the same term; it depends on the model happening to notice
both passages and reconcile them correctly in one pass.

**Harness mechanism:** The Contract Analyst records every clause as a
separate evidence item, without merging near-duplicates. `POLICY_CHECK`
explicitly looks for multiple evidence items sharing a `clause_type`
with differing values, applies the deterministic tie-break (see
[decisions.md](decisions.md) ADR-007: default to the more conservative,
company-favorable value), and flags the conflict - both source clauses
and the resolution - for human sign-off rather than presenting a single
number as if it were uncontested.

---

## 4. Inconsistent decisions across a negotiation

**What it looks like:** The system treats the same fact or the same
policy differently in round 1 versus round 3 of a negotiation (for
example, accepting Net 15 payment terms early on, then rejecting an
identical Net 15 proposal later without an explanation for the change).

**Why an LLM alone will not reliably catch it:** If negotiation state
lives only in a growing conversational context, there is no authoritative
record forcing every round to reference the same facts and the same
policy version. Longer context also increases the chance of the model
losing track of an earlier constraint.

**Harness mechanism:** Negotiation state (current round, positions,
history, violations, agent reviews) lives in a structured state store
outside the LLM's context window, tagged with a `policy_version`. Every
agent reads from and writes to this state explicitly, so round 3 is
evaluated against the same policy and the same evidence as round 1, not
against whatever the model happens to remember.

---

## 5. Silent clause omissions

**What it looks like:** The vendor contract never addresses a
policy-relevant term (for example, data ownership), and the negotiation
recommendation just does not mention it - or, worse, quietly assumes a
default in the vendor's favor.

**Why an LLM alone will not reliably catch it:** There is no strong
incentive for a language model to flag the *absence* of something; it is
far more natural for it to talk about what is there.

**Harness mechanism:** The Contract Analyst is required to emit a
`NOT_SPECIFIED` evidence entry for every policy-relevant clause type it
does not find in the contract, rather than skipping it. `POLICY_CHECK`
treats `NOT_SPECIFIED` as a distinct outcome - "cannot verify" - that is
surfaced in the negotiation strategy and the audit log as something
needing an explicit ask or an explicit default decision, never silently
passed over.

---

## 6. Low-confidence evidence used as fact

**What it looks like:** An extraction that the Contract Analyst itself
is not very sure about (for example, an ambiguous renewal clause with a
0.5 confidence score) gets cited by the Negotiation Agent with the same
certainty as a clause quoted verbatim from the contract.

**Why an LLM alone will not reliably catch it:** Once a fact is restated
in a sentence, the uncertainty behind it disappears; prose does not
carry a confidence interval unless something forces it to.

**Harness mechanism:** Every evidence item carries a numeric `confidence`
score from extraction. `POLICY_CHECK` deterministically compares each
score against a fixed **0.6 threshold** (see [decisions.md](decisions.md)
ADR-006). Anything below it is blocked from use in negotiation planning
and flagged in the audit log as "low-confidence - not used," rather than
being quietly treated as settled fact.

---

## Summary table

| Failure mode | Harness mechanism | State machine stage |
|---|---|---|
| Policy violation | Deterministic hard-constraint check | `POLICY_GATE` |
| Unsupported/invented claim | Mandatory evidence citation (`clause_id`) | `NEGOTIATION_PLANNING`, `RED_TEAM_REVIEW` |
| Missed contradiction | Multi-evidence conflict detection + tie-break | `POLICY_CHECK` |
| Inconsistent decisions | Structured, versioned state store | all stages |
| Silent clause omission | Mandatory `NOT_SPECIFIED` extraction | `CONTRACT_ANALYSIS`, `POLICY_CHECK` |
| Low-confidence evidence as fact | 0.6 confidence threshold, enforced in code | `POLICY_CHECK` |

Every row exists because trusting a single LLM call to self-report on
that failure mode is exactly the thing this project is arguing does not
work. The harness is the argument.
