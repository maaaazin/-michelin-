ContractGuard — Problem Statement

Title

ContractGuard: A Policy-Enforced Agentic Harness for Vendor Contract Negotiation

1. Problem

Vendor contract negotiation is a high-impact business process involving pricing, payment terms, liability, termination, service levels, data ownership, renewals, and other contractual obligations.

Companies rarely negotiate without boundaries. They typically have internal procurement, legal, finance, and business policies that define:

preferred terms

acceptable ranges

hard limits

non-negotiable clauses

escalation conditions

requirements for human approval

Traditional LLM-based contract assistants can read contracts and generate convincing negotiation recommendations, but they are not inherently reliable control systems.

A single LLM may:

overlook important clauses

miss contradictions between sections

make unsupported assumptions

forget or reinterpret company policy

propose concessions beyond authorized limits

produce malformed or incomplete structured output

reinforce its own incorrect reasoning

continue despite unresolved ambiguity

lack persistent, auditable state

The fundamental problem is therefore not simply:

"Can an LLM negotiate a contract?"

It is:

"How can an LLM participate in contract negotiation without being trusted to enforce its own boundaries?"

2. Proposed Solution

ContractGuard is an agentic contract negotiation system built around a dedicated harness.

Specialized AI agents perform reasoning tasks such as:

contract analysis

legal/risk analysis

financial/business analysis

negotiation strategy generation

independent red-team review

The harness surrounds these agents with deterministic controls for:

company policy enforcement

evidence grounding

structured state

permissions

validation

retry handling

failure routing

audit logging

human escalation

The central design principle is:

The LLM proposes; the harness verifies and decides whether the proposal is allowed to proceed.

3. Example

Suppose a company's policy says:

Annual price escalation:
Hard maximum = 5%

Payment:
Minimum = Net 30

Termination:
Maximum = 60 days

SLA:
Minimum = 99.9%

A vendor proposes:

Annual price escalation = 8%
Payment = Net 15
Termination = 180 days
SLA = 99.5%

The negotiation agent might propose:

"Accept 8% annual escalation in exchange for Net 60 payment terms."

A traditional LLM workflow may produce this as a reasonable compromise.

ContractGuard intercepts it:

POLICY GATE

Proposed escalation: 8%
Company maximum: 5%

❌ BLOCKED

Reason:
Hard policy constraint violated.

The harness records the violation and sends the workflow back for replanning.

The negotiation agent may then produce:

5% escalation
Net 60 payment
30-day termination
99.9% SLA

The harness validates the new proposal and allows it to continue if it passes all required checks.

4. Why a Harness Is Required

A conventional agent architecture looks like:

User
  |
  v
LLM
  |
  v
Tools
  |
  v
Answer

The model is responsible for both:

reasoning about the task, and

following the rules governing the task.

This creates a dangerous coupling.

ContractGuard separates these responsibilities:

LLM:
Reason
Analyze
Propose
Negotiate

HARNESS:
Validate
Enforce
Track state
Check evidence
Block
Retry
Replan
Escalate
Audit

This means the system does not depend on the LLM remembering every rule correctly.

5. Why Traditional LLM Agents Can Fail

Failure 1 — Policy drift

The model may understand a 5% maximum early in the interaction but later propose 8% because it considers the concession commercially attractive.

Failure 2 — Unsupported claims

The model may state that a contract provides a 99.9% SLA when the contract actually says 99.5%.

Failure 3 — Contradictory clauses

The contract may contain:

Section 4.2 → 5% maximum increase
Appendix B  → 15% increase at renewal

A single agent may overlook or silently resolve the contradiction.

Failure 4 — Self-verification

The same agent that creates a negotiation strategy may also decide that the strategy is correct.

This creates a weak feedback loop:

LLM proposes
   ↓
LLM reviews itself
   ↓
LLM approves itself

ContractGuard instead uses independent review.

Failure 5 — Agent/tool failure

PDF extraction, API calls, or structured generation may fail.

A conventional workflow may terminate.

ContractGuard can retry, fall back, or escalate.

Failure 6 — Memory/state drift

A long negotiation can contain many offers, rejections, and concessions.

Relying on conversational context alone makes it difficult to guarantee that every agent sees the same authoritative state.

ContractGuard stores negotiation state separately from the LLM.

6. Core Features

6.1 Contract Intelligence

Extract important clauses into structured evidence.

6.2 Company Negotiation Playbook

Represent company rules as structured policy.

6.3 Multi-Agent Analysis

Use specialized agents rather than one model performing every role.

6.4 Deterministic Policy Gate

Hard constraints are checked programmatically.

6.5 Evidence Grounding

Negotiation claims must reference contract evidence.

6.6 Independent Red Team

A separate agent challenges proposed negotiation moves.

6.7 Persistent Negotiation Memory

Store offers, responses, violations, decisions, and state.

6.8 Failure Recovery

Different failure types receive different recovery strategies.

6.9 Human Escalation

Unresolved ambiguity or disagreement results in human review rather than fabricated certainty.

6.10 Auditability

Every important decision can be traced to:

Decision
   ↓
Agent proposal
   ↓
Policy check
   ↓
Evidence
   ↓
Review
   ↓
Final outcome

7. Primary User

The primary users are organizations that negotiate contracts with external vendors, particularly:

procurement teams

sourcing teams

legal operations

finance/procurement operations

enterprise vendor-management teams

8. Primary User Journey

1. Upload vendor contract
          ↓
2. Load company negotiation policy
          ↓
3. Extract and normalize clauses
          ↓
4. Identify risks and policy conflicts
          ↓
5. Generate negotiation strategy
          ↓
6. Generate proposed counteroffer
          ↓
7. Policy Gate
          |
       +--+--+
       |     |
      PASS  FAIL
       |     |
       |   REPLAN
       |     |
       |     +----> New proposal
       |
       v
8. Independent Red-Team review
          |
       +--+--+
       |     |
      PASS  FAIL
       |     |
       |   REPLAN
       |
       v
9. Final negotiation recommendation
          ↓
10. Audit log

9. Hackathon Differentiation

Contract analysis and AI contract review already exist.

ContractGuard is differentiated by focusing on the execution harness.

The project is not:

"An AI that reads contracts."

It is:

"A controlled environment in which AI agents can negotiate contracts while the system independently enforces business boundaries."

The important innovation is therefore the combination of:

Multi-agent reasoning
        +
Deterministic policy enforcement
        +
Evidence verification
        +
Independent red teaming
        +
Persistent state
        +
Failure recovery
        +
Human escalation

10. Success Criteria

The prototype should demonstrate that:

Reliability

Invalid proposals are blocked rather than silently accepted.

Policy compliance

Hard constraints cannot be overridden by an LLM.

Evidence grounding

Important claims can be traced back to contract clauses.

Resilience

Recoverable failures trigger retries or replanning.

Graceful degradation

Unresolved conflicts result in human review.

Auditability

The complete negotiation path can be inspected.

Explainability

The system can explain why a proposal was blocked, accepted, or escalated.

11. Primary Hackathon Demo

The demo should deliberately create a situation where a naive LLM workflow can produce a risky recommendation.

Vendor contract

Annual fee: ₹20 lakh
Annual price escalation: 8%
Payment: Net 15
Termination: 180 days
Liability: ₹2 lakh
SLA: 99.5%

Company policy

Price escalation: maximum 5%
Payment: minimum Net 30
Termination: maximum 60 days
Liability: minimum annual contract value
SLA: minimum 99.9%

Adversarial contradiction

Section 4.2:
Annual escalation shall not exceed 5%.

Appendix B:
Vendor may increase fees by up to 15% at renewal.

Demonstration

First run:

TRADITIONAL LLM

Show its recommendation and identify where the architecture lacks enforcement.

Then run:

CONTRACTGUARD

Show:

Agent proposes 8%
        ↓
Policy Gate
        ↓
❌ BLOCKED
        ↓
Replan
        ↓
New proposal
        ↓
Red Team
        ↓
✓ APPROVED

The goal is not to prove that a particular model always fails.

The goal is to demonstrate:

A traditional LLM workflow relies on the model to behave correctly; ContractGuard structurally prevents invalid actions from proceeding.

12. Core Message

The project can be summarized in one sentence:

ContractGuard lets AI negotiate vendor contracts, but puts every AI-generated negotiation move through an enforceable policy, evidence, and independent-review harness before allowing it to proceed.

The key presentation line:

"We don't make the model smarter. We make it harder for the model to make an unsafe decision."