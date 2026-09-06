# WinWin — Methodology

## Build order

Build in this order. Each stage should be genuinely working (not just
written) before moving to the next one - a policy engine with no tests
run against it is not "done," it is unverified.

1. **Schemas** (`/schemas`) - Pydantic models for extracted evidence
   (`clause_type`, `vendor_value`, `unit`, `source_section`,
   `source_text`, `confidence`), company policy, negotiation state, and
   agent outputs. Get these right first: every agent and every harness
   component is going to be validated against them, so a schema change
   later is expensive in a way a prompt change is not.
2. **Policy engine** (`/harness`) - the deterministic comparisons: hard
   constraint checks, the 0.6 confidence threshold, `NOT_SPECIFIED`
   handling, and the contradiction tie-break rule. Write this in plain
   Python with unit tests against hand-written evidence fixtures, before
   any agent exists to produce that evidence. If the policy engine is
   correct against fixtures, it stays correct no matter what the LLM
   produces later.
3. **Agents** (`/agents`) - Contract Analyst first (everything downstream
   needs its output shape), then Legal/Risk and Business/Finance (can be
   built in parallel, they do not depend on each other), then
   Negotiation, then Red-Team last (it needs a proposal to challenge).
4. **Graph wiring** (`/app` or a top-level graph module) - wire the
   agents and the harness into the LangGraph state machine from
   architecture.md Section 6. Get the happy path (no violations, no
   contradictions, one round) working end to end before adding replan
   loops.
5. **Demo data** (`/data`) - the Acme Cloud Services vendor contract and
   company policy from architecture.md Section 11, including the
   deliberate Section 4.2 / Appendix B contradiction. Build this before
   the UI so the UI has something real to render.
6. **UI** (`/app`, Streamlit) - call the graph directly, in-process
   (ADR-002). Render the negotiation trace: proposal, policy check
   result, red-team findings, final outcome, audit log.
7. **Edge cases** - verify all three explicitly, with the demo data
   built to exercise them:
   - a clause the vendor contract does not mention (`NOT_SPECIFIED`)
   - evidence below the 0.6 confidence threshold
   - the Section 4.2 / Appendix B contradiction and its tie-break
8. **Polish** - error messages, audit log formatting, README setup
   instructions that actually work from a clean clone.
9. **Stretch goals**, in priority order (see
   [decisions.md](decisions.md) ADR-009): comparison mode (traditional
   single-LLM baseline, side by side) first, then Legal-vs-Risk
   disagreement escalation, then SQLite persistence. Do not start any of
   these while the core loop or the three edge cases are not fully
   working - a polished stretch goal on top of a broken core is a worse
   demo than a rough core with no stretch goals.

## The core rule

**Deterministic checks belong in code, not prompts.**

If a check can be written as a plain Python comparison - a number
against a threshold, a value against an enum, the presence or absence of
a key - it must be written that way, in `/harness`, with no LLM call in
the decision path. This is not a style preference; it is the entire
thesis of the project. A prompt that says "reject any escalation over
5%" is still just a request the model might not follow under pressure.
An `if proposed_value > policy.hard_max` in the policy engine cannot be
argued with.

LLM calls are for reasoning and strategy: extracting clauses from
unstructured text, assessing legal or commercial risk, proposing a
negotiation move, and independently critiquing a proposal. They are
never for deciding whether a number exceeds a threshold, whether a value
matches an enum, or whether a required field is present. See
[claude.md](claude.md) for the same rule phrased as a coding convention.

## Definition of done for the core build

The core loop is done when, using the demo data from architecture.md
Section 11, a single run through the graph:

- extracts all clauses, including emitting `NOT_SPECIFIED` for any
  policy-relevant clause absent from the contract,
- flags at least one piece of evidence below the 0.6 confidence
  threshold and excludes it from the negotiation proposal,
- detects the Section 4.2 / Appendix B contradiction, applies the
  tie-break, and flags it for human sign-off,
- has the negotiation agent propose an out-of-policy move at least once,
  gets it blocked by the policy gate, and produces a compliant proposal
  on replan,
- passes red-team review and the policy gate on the compliant proposal,
  and
- produces a final recommendation with a full audit trail from proposal
  through policy check, evidence, review, to outcome.

Only after all of that is true should stretch goals be attempted.
