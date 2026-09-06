# WinWin — Architecture

*(Working title. Formerly drafted as "ContractGuard"; repo directory is
currently `-michelin-`. See [decisions.md](decisions.md) ADR-001.)*

## 1. Overview

WinWin is an agentic contract negotiation system where LLM agents propose
analysis and negotiation moves, while a deterministic harness controls
what those agents are allowed to do.

Core principle:

> The LLM proposes; the harness verifies and decides whether the
> proposal is allowed to proceed.

This is a 4-hour hackathon build. The architecture below is the finalized
core scope — see [decisions.md](decisions.md) for what was deliberately
cut or deferred, and [methodology.md](methodology.md) for build order.

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
        |                 WARDEN HARNESS                    |
        |               (LangGraph graph)                   |
        |                                                    |
        |  State Store (in-memory dict)   Policy Engine      |
        |  Evidence Store                 Policy Gate        |
        |  Retry Manager                  Failure Router     |
        |  Audit Logger                                      |
        +---------------------+------------------------------+
                              |
        +---------------------+---------------------+
        |             |               |             |
        v             v               v             |
   Contract       Legal/Risk    Business/Finance     |
   Analyst          Agent            Agent           |
   Agent             |               |               |
        |            +-------+-------+               |
        |                    |                        |
        |                    v                        |
        |            Negotiation Agent <--------------+ (replan target)
        |                    |
        |                    v
        |            Proposed Move
        |                    |
        |                    v
        |            RED_TEAM_REVIEW  (Red-Team Agent)
        |                    |
        |                    v
        |             POLICY_GATE  (deterministic)
        |               /        \
        |             PASS       FAIL
        |              |           |
        |              v           +---> back to Negotiation Agent
        |            FINAL
        |              |
        +--------------+
                        v
                 AUDIT + OUTPUT
```

## 4. Agents

Five agents, kept separate on purpose (see ADR-003 on Legal vs Risk).

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

### 5.2 Policy Check vs. Policy Gate

WinWin's state machine (Section 6) has two distinct policy touchpoints
that do different jobs:

- **POLICY_CHECK** runs once, right after extraction, over the raw
  contract evidence. It is diagnostic: it compares every extracted clause
  to company policy and produces a list of issues (violations, gaps,
  contradictions, low-confidence facts) that feeds the negotiation
  strategy. It never blocks anything by itself.
- **POLICY_GATE** runs on every proposed negotiation move, after
  red-team review. It is a hard pass/fail check: any hard-constraint
  violation in the proposal itself, including one the red-team agent
  surfaced, fails the gate and sends the workflow back to
  `NEGOTIATION_PLANNING`. A passed gate is what allows a proposal to
  become the final recommendation.

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

Finalized flow (LangGraph):

```
START
  |
  v
CONTRACT_ANALYSIS     Contract Analyst extracts structured evidence
  |                   (NOT_SPECIFIED for absent clauses, confidence
  |                   score per fact)
  v
POLICY_CHECK          Deterministic: policy engine compares evidence to
  |                   company policy. Flags hard-constraint issues,
  |                   NOT_SPECIFIED clauses, sub-threshold-confidence
  |                   evidence, and contradictions (with tie-break
  |                   applied and recorded for sign-off). Diagnostic
  |                   only - does not block.
  v
NEGOTIATION_PLANNING  Legal/Risk + Business/Finance + Negotiation agents
  |                   produce a proposed move, grounded only in evidence
  |                   that cleared the confidence threshold.
  v
RED_TEAM_REVIEW       Red-Team Agent independently challenges the move
  |                   and attaches findings to the proposal.
  v
POLICY_GATE           Deterministic hard-constraint check on the
  |                   proposal, informed by red-team findings.
  |
  +---- FAIL ----> back to NEGOTIATION_PLANNING (replan)
  |
 PASS
  |
  v
FINAL                 Approved recommendation + audit trail
  |
  v
END
```

A bounded replan count (recommended: 3) prevents an infinite
propose-reject loop; exceeding it routes to human review instead of
looping forever.

This collapses an earlier two-gate draft (policy gate before *and* after
red-team review) into the single gate above — see ADR-008. Red-team
findings that amount to a hard-policy issue simply become one of the
reasons the one gate fails; softer, qualitative red-team concerns are
attached to the audit trail regardless of PASS/FAIL, for human visibility.

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
| Persistence (core) | in-memory dict |
| Persistence (stretch) | SQLite |

**Explicitly avoided:** FastAPI (ADR-002), Kubernetes, vector databases,
authentication, microservices, and RAG beyond straightforward structured
extraction. None of these serve a 4-hour build of this scope. Any new
dependency beyond the list above gets flagged before it is added (see
[claude.md](claude.md)).

## 11. Demo Scenario

Fictional vendor: Acme Cloud Services.

**Company policy:** escalation max 5%, payment min Net 30, termination
max 60 days, liability at least the annual contract value, SLA min 99.9%,
data ownership retained by the company.

**Vendor contract:** annual fee Rs 20 lakh, escalation 8%, payment Net 15,
termination 180 days, liability Rs 2 lakh, SLA 99.5%, 1-year auto-renewal.

**Built-in contradiction:** Section 4.2 caps escalation at 5%; Appendix B
allows the vendor to raise fees up to 15% at renewal.

## 12. Traditional LLM Baseline (comparison mode, stretch goal)

```
Contract + Policy -> single LLM call -> recommendation
```

No deterministic policy gate, no independent review, no persistent
structured state, no recovery mechanism. Useful as a side-by-side
demo if time allows (see ADR-009) — not a claim that any specific model
will always fail, just a demonstration that the architecture has no
structural enforcement.

## 13. WinWin Demonstration

```
Negotiation Agent proposes:
"Accept 8% annual escalation in exchange for Net 60 payment terms."

POLICY GATE
Proposed escalation: 8%   Maximum allowed: 5%
BLOCKED - hard constraint violation
Returning to NEGOTIATION_PLANNING...

New proposal: 5% escalation, Net 60 payment, 30-day termination,
99.9% SLA, liability at annual contract value.

RED_TEAM_REVIEW: passed
POLICY_GATE: passed
FINAL PROPOSAL APPROVED
```

## 14. Design Principle

WinWin is not trying to make an LLM perfectly reliable. It assumes the
LLM can fail and designs the execution environment to detect, contain,
recover from, and escalate those failures. That is the central
harness-engineering idea behind this project.
