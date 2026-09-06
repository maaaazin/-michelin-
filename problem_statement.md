# WinWin — Problem Statement

*(Final name for the demo. The project was drafted as "ContractGuard,"
built under the working title "Warden," and renamed to "WinWin" ahead of
the live demo; repo directory is still `-michelin-` and stays that way.
See [decisions.md](decisions.md) ADR-001 and ADR-013.)*

## 1. The Problem

Vendor contract negotiation is a high-impact business process covering
pricing, payment terms, liability, termination, service levels, data
ownership, renewals, and other contractual obligations.

Companies rarely negotiate without boundaries. Internal procurement,
legal, finance, and business policy typically defines:

- preferred terms and acceptable ranges
- hard limits that must never be crossed
- non-negotiable clauses
- conditions that require escalation or human approval

A representative policy:

| Term | Company rule |
|---|---|
| Price escalation | hard maximum 5% / year |
| Payment terms | minimum Net 30 |
| Termination notice | maximum 60 days |
| Liability cap | at least the annual contract value |
| SLA | minimum 99.9% uptime |
| Data ownership | must remain with the company |

Traditional LLM-based contract assistants can read a contract and generate
a convincing negotiation recommendation, but they are not inherently
reliable control systems. A single LLM call may:

- overlook important clauses
- miss contradictions between sections
- make unsupported assumptions
- forget or reinterpret company policy mid-conversation
- propose concessions beyond authorized limits
- produce malformed or incomplete structured output
- reinforce its own incorrect reasoning
- continue past unresolved ambiguity instead of flagging it
- lack persistent, auditable state across a multi-round negotiation

The question is therefore not:

> "Can an LLM negotiate a contract?"

It is:

> "How can an LLM participate in contract negotiation without being
> trusted to enforce its own boundaries?"

That question cannot be answered inside a single LLM call, no matter how
good the prompt is: the same call that proposes a move is the one that
would have to police it, using policy rules held only in its context
window and evidence it may or may not have actually read correctly. There
is no independent check between "the model said so" and "the move is
allowed." WinWin's answer is to move enforcement out of the prompt and
into code that runs around the model.

## 2. Proposed Solution

WinWin is an agentic contract negotiation system built around a
deterministic harness.

Specialized agents perform reasoning tasks:

- contract analysis (extraction)
- legal/risk analysis
- financial/business analysis
- negotiation strategy generation
- independent red-team review

The harness surrounds these agents with deterministic controls for:

- company policy enforcement
- evidence grounding
- structured state
- validation and retry handling
- failure routing
- audit logging
- human escalation

Central design principle:

> **The LLM proposes; the harness verifies and decides whether the
> proposal is allowed to proceed.**

## 3. Worked Example

Company policy: escalation max 5%, payment min Net 30, termination max 60
days, SLA min 99.9%.

Vendor contract: escalation 8%, payment Net 15, termination 180 days, SLA
99.5%.

A negotiation agent might propose:

> "Accept 8% annual escalation in exchange for Net 60 payment terms."

A traditional LLM workflow may accept this as a reasonable-sounding
compromise. WinWin intercepts it instead:

```
POLICY GATE
Proposed escalation: 8%
Company maximum:     5%
BLOCKED - hard policy constraint violated
```

The harness records the violation and routes the workflow back to
negotiation planning. The negotiation agent then produces a compliant
proposal (5% escalation, Net 60, 30-day termination, 99.9% SLA), which the
harness validates and allows to proceed.

## 4. Why a Harness Is Required

A conventional agent architecture is:

```
User -> LLM -> Tools -> Answer
```

The model is responsible for *both* reasoning about the task *and*
following the rules governing the task. That coupling is the failure
mode. WinWin separates the two:

| LLM does | Harness does |
|---|---|
| Reason, analyze, propose, negotiate | Validate, enforce, track state, check evidence, block, retry, replan, escalate, audit |

The system does not depend on the model remembering every rule correctly,
because the model is never the one deciding whether a rule was followed.

## 5. Why a Single LLM Call Structurally Cannot Enforce This

**Policy drift.** The model may understand a 5% maximum early in a
conversation but propose 8% later because it judges the concession
commercially attractive in the moment, with nothing forcing it to
re-check the original constraint before speaking.

**Unsupported claims.** The model may state the contract guarantees a
99.9% SLA when the source text actually says 99.5%. Nothing separates "I
recall reading X" from "X is literally quoted in the evidence."

**Contradictory clauses.** A contract may contain Section 4.2 capping
escalation at 5% and Appendix B allowing 15% at renewal. A single agent
may silently pick one, or blend them into a number neither clause
supports.

**Self-verification.** The same agent that creates a negotiation strategy
also deciding whether that strategy is sound is a closed loop: propose,
review yourself, approve yourself. It has no independent signal to catch
its own blind spots.

**Silent gaps.** If the vendor contract never mentions a clause (for
example, data ownership), a single LLM call will often just omit it too,
or worse, assume a default, rather than surfacing "this term is absent
and needs a decision."

**Low-confidence evidence treated as fact.** An extraction that is only
60% sure a clause means what it appears to mean can get relayed by the
model with the same confidence as a clause quoted verbatim, because
natural-language output does not carry a confidence score.

**Tool/state failures.** PDF extraction or structured generation can fail
outright. A conventional single-pass workflow has no retry or fallback
path and simply produces a bad answer or crashes.

**Memory/state drift.** A long negotiation involves many offers,
rejections, and concessions. Relying on conversational context alone
gives no guarantee that every agent is reasoning from the same
authoritative state.

WinWin's edge-case handling targets the sharpest versions of these
directly (see [architecture.md](architecture.md) Section 6 and
[failures.md](failures.md)):

1. A clause the vendor contract never mentions leads the extractor to
   emit `NOT_SPECIFIED`; the policy gate flags "cannot verify" rather
   than silently passing or failing it.
2. Extracted evidence below a 0.6 confidence threshold is blocked from
   use by the negotiation agent and flagged instead.
3. Two clauses that contradict each other are detected by the harness,
   which deterministically ties back to the more conservative,
   company-favorable constraint for negotiation purposes, and flags the
   conflict for human sign-off rather than silently picking a side.

## 6. Core Features

1. **Contract intelligence** — extract clauses into structured evidence.
2. **Company negotiation playbook** — represent company rules as
   structured policy, not prose.
3. **Multi-agent analysis** — specialized agents instead of one model
   performing every role.
4. **Deterministic policy gate** — hard constraints checked in plain code.
5. **Evidence grounding** — negotiation claims must cite contract
   evidence.
6. **Independent red team** — a separate agent challenges every proposed
   move.
7. **Negotiation state** — offers, responses, violations, and decisions
   tracked outside the model's context window.
8. **Failure recovery** — different failure types get different recovery
   strategies (retry, replan, escalate).
9. **Human escalation** — unresolved ambiguity or conflict produces a
   flag for a person, never fabricated certainty.
10. **Auditability** — every decision traces from proposal, through
    policy check and evidence, through review, to final outcome.

## 7. Primary User

Procurement, sourcing, legal operations, and finance/procurement
operations teams that negotiate contracts with external vendors.

## 8. Primary User Journey

```
Upload vendor contract
        |
Load company negotiation policy
        |
Extract and normalize clauses (structured evidence)
        |
Policy check: identify risks, gaps, and conflicts
        |
Generate negotiation strategy / counteroffer
        |
Red-team review
        |
Policy gate  --FAIL--> replan negotiation strategy
        |
       PASS
        |
Final negotiation recommendation + audit log
```

## 9. Hackathon Differentiation

Contract analysis and "AI contract review" tools already exist. WinWin is
differentiated by the execution harness, not the reading comprehension.

WinWin is not "an AI that reads contracts." It is a controlled environment
in which AI agents can negotiate contracts while the system independently
enforces business boundaries, combining multi-agent reasoning,
deterministic policy enforcement, evidence verification, independent
red-teaming, negotiation state, failure recovery, and human escalation.

## 10. Success Criteria

- **Reliability** — invalid proposals are blocked, not silently accepted.
- **Policy compliance** — hard constraints cannot be overridden by an LLM.
- **Evidence grounding** — claims trace back to contract clauses.
- **Resilience** — recoverable failures trigger retries or replanning.
- **Graceful degradation** — unresolved conflicts route to human review.
- **Auditability** — the full negotiation path can be inspected.
- **Explainability** — the system can explain why a proposal was blocked,
  accepted, or escalated.

## 11. Demo Scenario

The scenario below was the original plan; see
[architecture.md](architecture.md) Section 11 for what actually shipped -
six real vendor-contract and policy PDFs in `/test_docs`, each built to
exercise a specific harness mechanism (a genuinely clean contract, a
deliberately contradictory one, a straightforward policy-violation one,
and so on), run against the real compiled graph.

**Vendor contract:** annual fee Rs 20 lakh, escalation 8%, payment Net 15,
termination 180 days, liability Rs 2 lakh, SLA 99.5%.

**Company policy:** escalation max 5%, payment min Net 30, termination
max 60 days, liability at least the annual contract value, SLA min 99.9%.

**Adversarial contradiction:** Section 4.2 caps escalation at 5%; Appendix
B lets the vendor raise fees up to 15% at renewal. This is what
`contradictory_contract_demo.pdf` demonstrates for real.

The comparison-mode "traditional single-LLM baseline" side-by-side was
not built (it remained a stretch goal - ADR-009); the live demo runs
WinWin directly: the negotiation agent proposes an out-of-policy move,
the policy gate blocks it, the system replans, red-team review runs, and
either a final approved proposal comes out or - after 3 replan attempts -
the run escalates to human review with exactly what's still unresolved.

The point is not that a particular model will always fail. The point is
that a traditional LLM workflow *relies* on the model behaving correctly,
while WinWin *structurally prevents* invalid actions from proceeding
regardless of what the model does.

## 12. Core Message

> WinWin lets AI negotiate vendor contracts, but puts every AI-generated
> negotiation move through an enforceable policy, evidence, and
> independent-review harness before allowing it to proceed.

Presentation line: **"We do not make the model smarter. We make it harder
for the model to make an unsafe decision."**
