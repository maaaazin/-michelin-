ContractGuard — Architecture

1. Overview

ContractGuard is an agentic contract negotiation system where LLM agents propose analysis and negotiation moves, while a deterministic harness controls what those agents are allowed to do.

Core principle:

The LLM proposes; the harness verifies and decides whether the proposal is allowed to proceed.

The system is designed to demonstrate why a traditional single-LLM contract negotiation workflow is insufficient for consequential business decisions.

2. Goals

Extract and understand vendor contract clauses.

Compare contract terms against company negotiation policy.

Generate negotiation strategies and counteroffers.

Ground important decisions in contract evidence.

Prevent hard-policy violations.

Detect contradictory or unsupported claims.

Independently red-team proposed negotiation moves.

Maintain persistent negotiation state and history.

Retry recoverable failures.

Replan after policy violations.

Escalate unresolved ambiguity or agent disagreement to human review.

Produce an auditable record of what happened.

3. High-Level Architecture

                         USER
                           |
                           v
                  +----------------+
                  |    STREAMLIT   |
                  |       UI       |
                  +-------+--------+
                          |
                          v
                  +----------------+
                  |     FASTAPI    |
                  +-------+--------+
                          |
                          v
        +---------------------------------------+
        |              CONTRACTGUARD             |
        |                HARNESS                 |
        |                                       |
        |  State Store      Policy Engine       |
        |  Evidence Store   Policy Gate         |
        |  Retry Manager    Failure Router       |
        |  Audit Logger     Permission Control   |
        +-------------------+-------------------+
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
       Contract Agent   Legal/Risk    Business/Finance
                           Agent          Agent
              |             |             |
              +-------------+-------------+
                            |
                            v
                   Negotiation Agent
                            |
                            v
                    Proposed Move
                            |
                            v
                      POLICY GATE
                       /       \
                    PASS       FAIL
                     |           |
                     v           v
                 RED TEAM      REPLAN
                   AGENT          |
                     |            |
                 +---+---+        |
                 |       |        |
               PASS     FAIL <----+
                 |
                 v
             FINALIZE
                 |
                 v
            AUDIT + OUTPUT

4. Components

4.1 Contract Analyst Agent

Responsibilities:

Extract important clauses.

Normalize values.

Identify section/page references.

Return structured clause objects.

Flag ambiguity.

Preserve source evidence.

Example:

{
  "clause_type": "price_escalation",
  "vendor_value": 8,
  "unit": "percent",
  "source_section": "4.2",
  "source_text": "Annual fees may increase by 8%...",
  "confidence": 0.96
}

The agent should never be the sole authority for deterministic policy checks.

4.2 Legal/Risk Agent

Responsibilities:

Identify legally/commercially risky clauses.

Analyze liability, indemnity, termination, renewal, SLA, data ownership, etc.

Explain risks using contract evidence.

Flag clauses requiring human/legal review.

It should return structured findings with evidence references.

4.3 Business/Finance Agent

Responsibilities:

Evaluate price and payment terms.

Estimate commercial impact.

Compare vendor position with company targets.

Suggest economically meaningful trade-offs.

4.4 Negotiation Agent

Responsibilities:

Build a negotiation strategy.

Propose counteroffers.

Decide which soft constraints may be traded.

Use company targets and vendor position.

Reference supporting contract clauses.

Important:

The Negotiation Agent does not have authority to override company policy.

It can propose an invalid action; the harness must reject it.

4.5 Red-Team Agent

The Red-Team Agent independently challenges a proposed negotiation strategy.

It checks for:

Hard-policy violations.

Unsupported claims.

Missed contract risks.

Contradictory clauses.

Accidental concessions.

Inconsistency with negotiation history.

Unfavorable trade-offs.

It should not simply repeat the Negotiation Agent's reasoning.

5. The Harness

The harness is the core of ContractGuard.

5.1 Policy Engine

Company negotiation policy is represented as structured data.

Example:

{
  "price_escalation": {
    "target": 3,
    "hard_max": 5
  },
  "payment_terms_days": {
    "target": 60,
    "hard_min": 30
  },
  "termination_days": {
    "target": 30,
    "hard_max": 60
  },
  "liability": {
    "hard_min": "annual_contract_value"
  },
  "sla": {
    "hard_min": 99.9
  },
  "data_ownership": {
    "required": "company"
  }
}

Hard constraints must be checked deterministically in code.

Do not ask an LLM whether 8 > 5.

5.2 Policy Gate

Every proposed negotiation move passes through the Policy Gate.

Example:

Proposed price escalation: 8%
Company hard maximum: 5%

RESULT: BLOCKED
REASON: Hard constraint violation

A blocked proposal cannot become the final recommendation.

5.3 Evidence Store

Important contract facts are stored with their source.

Example:

{
  "clause_id": "CL-014",
  "type": "sla",
  "value": "99.5%",
  "section": "8.1",
  "page": 12,
  "source_text": "Vendor guarantees 99.5% uptime."
}

Negotiation proposals should reference these clause IDs.

This makes the final recommendation traceable.

5.4 State Store

The harness maintains structured negotiation state.

Example:

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

The LLM's conversational context is not treated as the system's source of truth.

5.5 Retry Manager

Recoverable failures should be retried with a bounded retry count.

Example:

Agent output invalid
      |
      v
Retry #1
      |
      v
Still invalid?
      |
      v
Retry #2
      |
      v
Still invalid?
      |
      v
Human review / graceful failure

Recommended initial limit: 2 retries.

5.6 Failure Router

Different failures should produce different recovery behavior.

Failure
  |
  +-- Invalid schema ------> Retry
  |
  +-- Tool/PDF failure ----> Retry / fallback
  |
  +-- Policy violation ----> Replan
  |
  +-- Evidence mismatch ---> Verify / re-extract
  |
  +-- Agent disagreement --> Independent verification
  |
  +-- Unresolved conflict -> Human review

5.7 Audit Logger

Every meaningful state transition should be logged.

Example:

10:31:02 Contract uploaded
10:31:05 18 clauses extracted
10:31:07 Company policy loaded
10:31:09 4 policy issues found
10:31:12 Negotiation strategy generated
10:31:15 Proposal rejected by Policy Gate
10:31:18 Negotiation replanned
10:31:21 Red-Team review passed
10:31:22 Final proposal generated

6. State Machine

Recommended LangGraph flow:

START
  |
  v
EXTRACT_CONTRACT
  |
  +---- failure ----> RETRY / HUMAN_REVIEW
  |
  v
VALIDATE_EVIDENCE
  |
  v
LOAD_POLICY
  |
  v
ANALYZE_CONTRACT
  |
  v
CREATE_NEGOTIATION_STRATEGY
  |
  v
POLICY_GATE
  |
  +---- FAIL ----> REPLAN
  |                   |
  |                   +----> POLICY_GATE
  |
  v
RED_TEAM_REVIEW
  |
  +---- FAIL ----> REPLAN
  |
  v
FINALIZE
  |
  v
AUDIT + OUTPUT
  |
  v
END

7. Failure Handling

Invalid LLM output

Use Pydantic validation.

If the agent does not produce the required schema:

Reject output.

Retry with corrective instruction.

Stop after retry budget.

Escalate if still unresolved.

Policy violation

Do not retry the same output.

Instead:

Record violation.

Explain violated constraint.

Return to negotiation planning.

Ask for a new proposal.

Re-run Policy Gate.

Contradictory contract clauses

If two clauses conflict:

Store both as evidence.

Mark the conflict.

Ask an independent verification agent to resolve if possible.

If unresolved, require human review.

Agent disagreement

If independent agents disagree on a material issue:

Record both positions.

Retrieve the supporting evidence.

Attempt independent verification.

Escalate if confidence remains low.

Infinite loops

Use:

maximum negotiation rounds

maximum retries per node

maximum replans

terminal human-review state

8. Memory Architecture

Working memory

LangGraph state for the current execution.

Persistent memory

SQLite for:

negotiation state

contract metadata

extracted clauses

proposals

violations

reviews

audit events

Historical memory

Optional future feature:

previous negotiations

vendor behavior

accepted/rejected concessions

historical outcomes

Historical memory is not required for the initial hackathon prototype.

9. Security / Authority Model

The most important authority rule:

Agents can PROPOSE.
Harness can ALLOW or BLOCK.

Agents should not be able to:

modify company hard constraints

delete audit logs

approve their own policy violations

modify historical negotiation state

bypass the Policy Gate

The policy should be loaded independently of the Negotiation Agent.

10. Recommended Tech Stack

Backend

Python

FastAPI

LangGraph

Pydantic

LLM

Gemini API or another available LLM API

Document processing

PyMuPDF

Persistence

SQLite

Frontend

Streamlit

Optional

Docker

.env for API keys

Avoid adding a vector database, complex authentication, microservices, or other infrastructure unless it becomes necessary.

11. Demo Scenario

Use a fictional vendor such as Acme Cloud Services.

Company policy

Price escalation: max 5%
Payment: minimum Net 30
Termination: max 60 days
Liability: at least annual contract value
SLA: minimum 99.9%
Data ownership: company

Vendor contract

Annual fee: ₹20 lakh
Price escalation: 8%
Payment: Net 15
Termination: 180 days
Liability: ₹2 lakh
SLA: 99.5%
Auto-renewal: 1 year

Add a contradiction:

Section 4.2:
Annual escalation shall not exceed 5%.

Appendix B:
Vendor may increase fees by up to 15% at renewal.

12. Traditional LLM Baseline

Baseline:

Contract + Policy
       |
       v
Single LLM
       |
       v
Recommendation

The baseline has no deterministic policy gate, independent review, persistent structured state, or recovery mechanism.

Do not claim that every traditional LLM will definitely fail a particular example. Instead demonstrate that the architecture has no structural enforcement mechanism.

13. ContractGuard Demonstration

Example invalid proposal:

Negotiation Agent:

"We can accept 8% annual escalation if the vendor
provides Net 60 payment terms."

Harness:

POLICY GATE

Proposed escalation: 8%
Maximum allowed: 5%

❌ BLOCKED
Hard constraint violation.

Returning to negotiation planner...

New proposal:

5% annual escalation
Net 60 payment
30-day termination
99.9% SLA
Liability at annual contract value

Harness:

✓ Policy passed
✓ Evidence supported
✓ Red-team passed

FINAL PROPOSAL APPROVED

This is the primary demonstration of why the harness is necessary.

14. Design Principle

ContractGuard is not trying to make an LLM perfectly reliable.

Instead:

It assumes the LLM can fail and designs the execution environment to detect, contain, recover from, and escalate those failures.

That is the central harness-engineering idea.