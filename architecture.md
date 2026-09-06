# WinWin — Architecture

*(Final name for the demo. The project was drafted as "ContractGuard,"
built under the working title "Warden," and renamed to "WinWin" ahead of
the live demo; repo directory is still `-michelin-` and stays that way.
See [decisions.md](decisions.md) ADR-001 and ADR-013.)*

## 1. Overview

WinWin is an agentic contract negotiation system where LLM agents propose
analysis and negotiation moves, while a deterministic harness controls
what those agents are allowed to do.

Core principle:

> The LLM proposes; the harness verifies and decides whether the
> proposal is allowed to proceed.

This started as a 4-hour hackathon build; the architecture below now
describes the system as actually built and demo-ready, not just the
planned scope — see [decisions.md](decisions.md) for what was
deliberately cut, deferred, or changed along the way, and
[methodology.md](methodology.md) for the build order that was followed.

## 2. Goals

- Extract and understand vendor contract clauses as structured evidence.
- Compare contract terms against company negotiation policy.
- Generate negotiation strategies and counteroffers.
- Ground every important claim in contract evidence.
- Prevent hard-policy violations from reaching a final recommendation.
- Detect contradictory, missing, or low-confidence evidence and handle
  each differently rather than treating them all as failures.
- Independently red-team proposed negotiation moves.
- Maintain negotiation state outside the LLM's context window.
- Replan after policy violations instead of retrying blindly.
- Flag unresolved ambiguity for human review.
- Produce an auditable record of what happened and why.

## 3. High-Level Architecture

Streamlit calls the LangGraph graph directly, in-process. There is no API
layer between the UI and the harness (see ADR-002) — this is a hackathon
prototype, not a multi-client service, so the extra hop bought nothing.

```
                              USER
                               |
                               v
                      +------------------+
                      |  STREAMLIT UI    |
                      +--------+---------+
                               | direct in-process call
                               v
        +--------------------------------------------------+
        |                 WINWIN HARNESS                    |
        |               (LangGraph graph)                   |
        |                                                    |
        |  State Store (in-memory dict)   Policy Engine      |
        |  Evidence Store                 Policy Gate        |
        |  Grounding Check                Failure Router     |
        |  Audit Logger                                      |
        +---------------------+------------------------------+
                              |
                              v
                    Policy Analyst Agent   (only if a policy PDF was
                              |              uploaded; else the default
                              v              policy_config.json is used)
                    Contract Analyst Agent
                              |
                              v
                       POLICY_CHECK  (deterministic, diagnostic)
                              |
                              v
              +---------------+---------------+
              v                               v
        Legal/Risk Agent              Business/Finance Agent
              |                               |
              +---------------+---------------+
                              v
                    Negotiation Agent  <---------------+ (replan target,
                              |                          up to 3 times)
                              v                          |
                       Proposed Move                     |
                              |                           |
                              v                           |
                    Red-Team Agent (independent review)   |
                              |                           |
                              v                           |
                       POLICY_GATE  (deterministic;       |
                        fails on any hard violation        |
                        OR a Red-Team REJECT)              |
                        /              \                   |
                      PASS             FAIL ----------------+
                       |                 |
                       v                 v (only after 3 failed replans)
                     FINAL          HUMAN_REVIEW
                       |                 |
                       +--------+--------+
                                v
                        AUDIT + OUTPUT
```

## 4. Agents

Six agents, kept separate on purpose (see ADR-003 on Legal vs Risk).

### 4.0 Policy Analyst Agent

- Runs first, and only when a company policy PDF is uploaded (otherwise
  the graph uses `data/policy_config.json` unchanged).
- Extracts only the numeric target/hard-limit value and a confidence
  score per rule type from the document text; the structural fields
  (comparison direction, unit, description) always come from the shipped
  default template, never re-derived by the model (ADR-014).
- Below a 0.7 confidence threshold, or if a rule type isn't found at all,
  that rule falls back to the default rather than guessing, and is
  tagged so the UI can show the user exactly which rules came from their
  document.

### 4.1 Contract Analyst Agent

- Extracts clauses from the vendor contract into structured evidence.
- Normalizes values (percentages, day counts, currency).
- Preserves section/page references and the exact source text.
- Emits `NOT_SPECIFIED` for any policy-relevant clause the contract does
  not address, instead of leaving it out.
- Attaches a confidence score per extracted fact.
- Never resolves contradictions itself — it reports both clauses; the
  harness resolves them (Section 6.3).

Example evidence item (also the schema baseline — see
[schemas](schemas/)):

```json
{
  "clause_type": "price_escalation",
  "vendor_value": 8,
  "unit": "percent",
  "source_section": "4.2",
  "source_text": "Annual fees may increase by 8%...",
  "confidence": 0.96
}
```

The Contract Analyst Agent is never the sole authority for a deterministic
policy check — it supplies facts; it does not judge them against policy.

### 4.2 Legal/Risk Agent

- Identifies legally and commercially risky clauses (liability, indemnity,
  termination, renewal, SLA, data ownership).
- Explains risk using cited evidence.
- Flags clauses that need human/legal review.

### 4.3 Business/Finance Agent

- Evaluates price and payment terms.
- Estimates commercial impact of the vendor's position vs. company
  targets.
- Suggests economically meaningful trade-offs.

Legal/Risk and Business/Finance stay as two agents rather than one merged
"risk" agent. Their independent, sometimes conflicting judgment is part of
the design — see ADR-003 and ADR-004 (the disagreement-escalation path is
a stretch goal, not core).

### 4.4 Negotiation Agent

- Builds a negotiation strategy and proposes counteroffers, using only
  evidence that passed the confidence and policy checks.
- Decides which soft constraints may be traded.
- Cites the contract evidence supporting each proposed term.
- Has **no authority** to override company policy. It can propose an
  invalid move; the harness is what rejects it.

### 4.5 Red-Team Agent

Independently challenges the proposed move before it reaches the policy
gate. Checks for:

- hard-policy violations the negotiation agent introduced
- unsupported claims (not backed by cited evidence)
- missed contract risks
- contradictory clauses the proposal glossed over
- accidental concessions
- inconsistency with prior rounds in negotiation history

It must not simply restate the Negotiation Agent's own reasoning — it is
a separate prompt with an adversarial framing, checking the same evidence
independently.

Its verdict is a hard gate (Section 5.2): a REJECT alone fails
`POLICY_GATE`, same as a hard-policy violation. That makes prompt
calibration load-bearing, not cosmetic — an adversarial framing with no
counter-instruction for the genuinely-clean case can reject a compliant
proposal indefinitely. The prompt requires every REJECT to cite a
specific item from the evidence given (a policy result, a named review
concern, or an internal contradiction); absent that, the verdict must be
ACCEPT (ADR-015).

## 5. The Harness

The harness is deterministic Python. No LLM call ever decides whether a
number crosses a threshold (see ADR-006 and [claude.md](claude.md)).

### 5.1 Policy Engine

Company policy is structured data, not prose:

```json
{
  "price_escalation": { "target": 3, "hard_max": 5 },
  "payment_terms_days": { "target": 60, "hard_min": 30 },
  "termination_days": { "target": 30, "hard_max": 60 },
  "liability": { "hard_min": "annual_contract_value" },
  "sla": { "hard_min": 99.9 },
  "data_ownership": { "required": "company" }
}
```

### 5.2 Policy Extraction, Policy Check, and Policy Gate

WinWin's state machine (Section 6) has three distinct policy touchpoints
that do different jobs:

- **POLICY_EXTRACTION** runs first, and only does anything if a company
  policy PDF was uploaded — otherwise the graph leaves the shipped
  `data/policy_config.json` untouched. When it runs, it produces the
  `PolicyConfig` every later stage checks against (ADR-014).
- **POLICY_CHECK** runs once, right after contract extraction, over the
  raw contract evidence. It is diagnostic: it compares every extracted
  clause to company policy and produces a list of issues (violations,
  gaps, contradictions, low-confidence facts) that feeds the negotiation
  strategy. It never blocks anything by itself.
- **POLICY_GATE** runs on every proposed negotiation move, after
  red-team review. It is a hard pass/fail check: any hard-constraint
  violation in the proposal itself, or a Red-Team `REJECT` verdict
  (Section 4.5), fails the gate and sends the workflow back to
  `NEGOTIATION_PLANNING`. A passed gate is what allows a proposal to
  become the final recommendation.

`POLICY_CHECK` and `POLICY_GATE` are the same underlying function
(`harness/policy_gate.py:run_policy_check`), called with and without a
proposed move — one implementation, not two to keep in sync.

```
POLICY GATE
Proposed escalation: 8%
Company hard maximum: 5%
RESULT: BLOCKED
REASON: hard constraint violation
```

### 5.3 Evidence Store

```json
{
  "clause_id": "CL-014",
  "type": "sla",
  "value": "99.5%",
  "section": "8.1",
  "source_text": "Vendor guarantees 99.5% uptime.",
  "confidence": 0.94
}
```

Negotiation proposals reference these clause IDs, which is what makes the
final recommendation traceable back to source text.

### 5.4 State Store

In-memory Python dict for the hackathon core (SQLite persistence is a
stretch goal — ADR-005). Structure:

```json
{
  "negotiation_id": "NG-001",
  "contract_id": "CTR-001",
  "policy_version": "v1",
  "current_round": 3,
  "current_state": "RED_TEAM_REVIEW",
  "company_position": {},
  "vendor_position": {},
  "negotiation_history": [],
  "violations": [],
  "agent_reviews": []
}
```

The LLM's conversational context is never treated as the system's source
of truth. Every agent reads and writes this state explicitly.

### 5.5 Retry Manager

Recoverable failures (invalid schema, transient API error) get a bounded
retry, not an infinite loop: 2 retries, then escalate to human review /
graceful failure.

### 5.6 Failure Router

Different failures get different recovery behavior:

```
Invalid schema        -> retry
Tool/PDF failure       -> retry / fallback
Policy violation        -> replan (back to NEGOTIATION_PLANNING)
Contradiction detected  -> deterministic tie-break + flag for human sign-off
Low-confidence evidence -> block from use, flag
Unresolved conflict     -> human review
```

### 5.7 Audit Logger

Every meaningful state transition is logged, e.g.:

```
10:31:02  Contract uploaded
10:31:05  18 clauses extracted
10:31:07  Company policy loaded
10:31:09  4 policy issues found (1 contradiction, 1 NOT_SPECIFIED)
10:31:12  Negotiation strategy generated
10:31:15  Proposal rejected by Policy Gate (escalation 8% > 5%)
10:31:18  Negotiation replanned
10:31:21  Red-Team review passed
10:31:22  Policy Gate passed
10:31:22  Final proposal generated
```

## 6. State Machine

As implemented in `harness/graph.py` (9 LangGraph nodes; `NegotiationStage`
in `schemas/negotiation.py` names each stage):

```
START
  |
  v
POLICY_EXTRACTION      Runs unconditionally, but only acts if a policy
  |                    PDF was uploaded (Policy Analyst extracts a
  |                    PolicyConfig); otherwise leaves the default
  |                    data/policy_config.json untouched.
  v
CONTRACT_ANALYSIS      Contract Analyst extracts structured evidence
  |                    (NOT_SPECIFIED for absent clauses, a confidence
  |                    score per fact).
  v
POLICY_CHECK           Deterministic: policy engine compares evidence to
  |                    company policy. Flags hard-constraint issues,
  |                    NOT_SPECIFIED clauses, sub-threshold-confidence
  |                    evidence, and contradictions (with tie-break
  |                    applied and recorded for sign-off). Diagnostic
  |                    only - does not block.
  v
(initial reviews)      Legal/Risk Agent and Business/Finance Agent each
  |                    independently review the extracted evidence and
  |                    policy check results once, in parallel intent
  |                    (sequential calls, independent prompts). Not
  |                    re-run on a replan - only NEGOTIATION_PLANNING
  |                    through POLICY_GATE loops.
  v
NEGOTIATION_PLANNING <--------------------------------------------+
  |                    Negotiation Agent proposes a move, grounded      |
  |                    only in evidence that cleared the confidence     |
  |                    threshold and passed harness/grounding_check.py. | (replan
  v                                                                     |  target,
RED_TEAM_REVIEW        Red-Team Agent independently challenges the      |  up to
  |                    proposal (Section 4.5).                         |  MAX_REPLANS
  v                                                                     |  = 3 times)
POLICY_GATE            Deterministic: hard-constraint check on the      |
  |                    proposal, OR a Red-Team REJECT verdict - either  |
  |                    alone fails the gate.                           |
  |                                                                     |
  +---- FAIL, replans used < 3 ----> back to NEGOTIATION_PLANNING ------+
  |
  +---- FAIL, replans used = 3 ----> HUMAN_REVIEW ----> END
  |
 PASS
  |
  v
FINAL                  Approved recommendation + audit trail
  |
  v
END
```

`HUMAN_REVIEW` is the graceful-degradation terminal state added beyond
the original draft: if the replan loop cannot reach an approvable
proposal within `MAX_REPLANS = 3` attempts, the graph stops and surfaces
exactly what remains unresolved (which rules are still `BLOCKED` /
`CONFLICTING`, and the Red-Team's last objection) rather than looping
forever or forcing a bad approval.

This collapses an earlier two-gate draft (policy gate before *and* after
red-team review) into the single gate above — see ADR-008. A Red-Team
`REJECT` alone fails the one gate; softer, qualitative red-team concerns
on an otherwise-passing proposal are attached to the audit trail
regardless of PASS/FAIL, for human visibility. Getting the Red-Team
Agent's prompt calibrated so it doesn't reject a genuinely clean proposal
turned out to be load-bearing, not cosmetic — see Section 4.5 and
ADR-015.

## 7. Core Edge Cases

These three are built into the harness from the start, not bolted on
later. See [failures.md](failures.md) for the full failure-mode mapping.

### 7.1 Clause not mentioned in the vendor contract

The Contract Analyst emits `clause_type: X, vendor_value: NOT_SPECIFIED`
instead of guessing or omitting the clause. `POLICY_CHECK` treats
`NOT_SPECIFIED` as its own outcome, distinct from pass/fail: "cannot
verify — needs an explicit ask or a default position," surfaced to the
negotiation agent and the audit log rather than silently defaulting.

### 7.2 Low-confidence evidence

Every extracted fact carries a `confidence` score. `POLICY_CHECK` compares
each score to a **hard threshold of 0.6** (ADR-006). Anything below it is
blocked from being cited as fact by the Negotiation Agent and is flagged
in the audit log as "low-confidence — not used." This is a deterministic
comparison in code, not a judgment call left to a prompt.

### 7.3 Contradictory clauses

Example: Section 4.2 caps escalation at 5%; Appendix B allows the vendor
to raise fees up to 15% at renewal. The Contract Analyst records both as
separate evidence items rather than merging or picking one.
`POLICY_CHECK` detects that two evidence items address the same
`clause_type` with different values, applies a deterministic tie-break —
**default to the more conservative, company-favorable constraint for
negotiation purposes** (ADR-007) — and records the conflict, both source
clauses, and the tie-break outcome as a flag requiring human sign-off
before the final recommendation is presented as final. The system does
not silently pick a side.

## 8. Memory Architecture

- **Working memory** — LangGraph state for the current execution.
- **Persistent memory (core)** — an in-memory Python dict, scoped to the
  running Streamlit session. Acceptable for a live demo; lost on
  restart. See ADR-005.
- **Persistent memory (stretch)** — SQLite for negotiation state,
  contract metadata, extracted clauses, proposals, violations, reviews,
  and audit events, if time allows.
- **Historical memory (future, out of scope)** — prior negotiations,
  vendor behavior patterns, historical outcomes. Not attempted in this
  build.

## 9. Security / Authority Model

> Agents can PROPOSE. The harness can ALLOW or BLOCK.

Agents cannot:

- modify company hard constraints
- delete audit logs
- approve their own policy violations
- modify historical negotiation state
- bypass the policy gate

Company policy is loaded independently of the Negotiation Agent and is
never something an agent call can rewrite.

## 10. Tech Stack

| Layer | Choice |
|---|---|
| Language | Python |
| Orchestration | LangGraph |
| LLM | OpenAI API (model set via one config constant, default `gpt-4o-mini`, override with `OPENAI_MODEL`) |
| Document processing | PyMuPDF |
| Validation / schemas | Pydantic |
| Frontend | Streamlit (calls the graph directly, in-process) |
| Tables / UI data | pandas (dataframes, `Styler` for status coloring) |
| Persistence (core) | in-memory dict |
| Persistence (stretch) | SQLite |

**Explicitly avoided:** FastAPI (ADR-002), Kubernetes, vector databases,
authentication, microservices, and RAG beyond straightforward structured
extraction. None of these serve a 4-hour build of this scope. Any new
dependency beyond the list above gets flagged before it is added (see
[claude.md](claude.md)).

## 11. Demo Data

The original plan (below, superseded) was a single fictional vendor with
a hand-built contradiction. What actually shipped is six real PDFs in
`/test_docs`, each built to exercise a specific harness mechanism, run
against the default `data/policy_config.json` unless noted:

| File | What it demonstrates |
|---|---|
| `clean_pass_demo.pdf` | Fully policy-compliant contract - the genuine happy path; reaches `FINAL` with 0 replans (ADR-015). |
| `contradictory_contract_demo.pdf` | Multiple clauses disagree with themselves (escalation, termination, liability cap, auto-renewal all `CONFLICTING`) plus a hard `BLOCKED` data-ownership clause - the contradiction-detection story. |
| `failure_demo_policyViolation.pdf` | Several straightforward hard-policy violations for the Negotiation Agent to resolve, with Red-Team catching its early arithmetic mistakes across replans. |
| `hidden_risk_demo.pdf` | Mostly compliant with one persistent `BLOCKED` data-ownership clause the negotiation agent repeatedly fails to actually fix. |
| `happy_path_demo.pdf` | Named for the original intent, but the contract itself states 3 different price-escalation values and 2 different termination-notice values across sections - so it escalates to `HUMAN_REVIEW` too. Kept as-is; `clean_pass_demo.pdf` is the real happy path now. |
| `playbook (1).pdf` | A company policy document (not a contract) - Apex Manufacturing's own vendor-negotiation playbook. Extracted via the Policy Analyst and applied to `happy_path_demo.pdf`'s contract text, exercising `POLICY_EXTRACTION`. |

Run all six against the real graph with `tests/manual_test_real_pdfs.py`;
run just the compliance check with `tests/manual_test_clean_contract.py`.

**Original planning scenario (fictional, not built as PDFs):** vendor
Acme Cloud Services, annual fee Rs 20 lakh, escalation 8%, payment Net 15,
termination 180 days, liability Rs 2 lakh, SLA 99.5%, 1-year auto-renewal,
against a policy of escalation max 5%, payment min Net 30, termination
max 60 days, liability at least the annual contract value, SLA min 99.9%,
data ownership retained by the company, with a built-in contradiction
(Section 4.2 caps escalation at 5%; Appendix B allows the vendor to raise
fees up to 15% at renewal). `contradictory_contract_demo.pdf` above is
the real analog of this scenario.

## 12. Traditional LLM Baseline (comparison mode, stretch goal)

**Not built.** Remains a stretch-goal idea only (ADR-009) - the core loop
and edge cases took the full build, so this was never started.

```
Contract + Policy -> single LLM call -> recommendation
```

No deterministic policy gate, no independent review, no persistent
structured state, no recovery mechanism. Would be useful as a
side-by-side demo if built — not a claim that any specific model will
always fail, just a demonstration that the architecture has no
structural enforcement.

## 13. WinWin Demonstration

A real audit trail from `clean_pass_demo.pdf` (Section 11) reaching
`FINAL` with 0 replans, captured live via `tests/manual_test_real_pdfs.py`:

```
Using default company policy (data/policy_config.json).
Contract uploaded; 8 clause(s) extracted.
Policy check complete: 7 PASS.
Legal/Risk review: ACCEPT.
Business/Finance review: ACCEPT.
Negotiation strategy generated.
Red-Team ACCEPT: The proposal accurately reflects compliance with all
company policies, as evidenced by all policy check results being marked
as PASS. Both the Legal/Risk and Business/Finance reviews are also
ACCEPT, confirming that there are no legal risks, ambiguities, or
operational concerns with the proposed terms. There are no contradictions
or ignored items within the proposal. Therefore, the negotiation proposal
is sound and should be accepted.
Policy gate PASSED (price_escalation=PASS; payment_terms_days=PASS;
termination_notice_days=PASS; liability_cap=PASS; sla_uptime=PASS;
data_ownership=PASS; auto_renewal_cancellation_window_days=PASS);
Red-Team ACCEPT. Final proposal approved.
Final proposal approved.
```

For the replan-and-block story, run `contradictory_contract_demo.pdf` or
`failure_demo_policyViolation.pdf` (Section 11) - each produces a real
`POLICY_GATE FAILED ... Replanning` trace followed by either a corrected
proposal or, after 3 attempts, escalation to `HUMAN_REVIEW`.

## 14. Design Principle

WinWin is not trying to make an LLM perfectly reliable. It assumes the
LLM can fail and designs the execution environment to detect, contain,
recover from, and escalate those failures. That is the central
harness-engineering idea behind this project.
