# Warden — Decisions Log (ADR-style)

Each entry: Status, Context, Decision, Consequences. Numbered
chronologically; do not renumber or delete old entries even if later ones
supersede them — mark them superseded instead.

---

## ADR-001: Working project name is "Warden"

**Status:** Accepted

**Context:** The repo was seeded with docs drafted under the name
"ContractGuard." The team's working title going into the build is
"Warden." The GitHub repo directory itself is named `-michelin-` (a
placeholder from repo creation) and has not been renamed.

**Decision:** Use "Warden" as the product name in all docs and, once code
exists, in the app UI and package names. Leave the GitHub repo directory
name (`-michelin-`) alone for now — renaming a GitHub repo mid-hackathon
is a distraction, not a blocker. Rename it later if a different name is
picked.

**Consequences:** Older references to "ContractGuard" in commit history
or early drafts are historical and not the current name. Anyone joining
the repo should treat "Warden" as authoritative going forward.

---

## ADR-002: Drop the FastAPI layer

**Status:** Accepted

**Context:** The original architecture draft put a FastAPI service
between the Streamlit UI and the LangGraph harness. For a single-user
hackathon demo running entirely on one machine, that is an extra network
hop, an extra process to run, and an extra source of bugs, with no
client other than the Streamlit app itself to justify it.

**Decision:** Streamlit calls the LangGraph graph directly, in-process.
No API layer.

**Consequences:** Simpler to run (one process, `streamlit run`), simpler
to debug (no serialization boundary between UI and harness state), and
fewer dependencies. If Warden ever needs a non-Streamlit client, an API
layer can be added later without changing the harness itself, since the
graph is already a self-contained callable.

---

## ADR-003: Keep Legal and Risk as separate agents

**Status:** Accepted

**Context:** Legal review (contractual/legal risk: liability, indemnity,
termination language) and risk review (commercial/operational risk) are
related but not identical judgments. Merging them into one "risk agent"
would be simpler to build but would remove the possibility of the two
disagreeing.

**Decision:** Keep the Legal/Risk Agent and the Business/Finance Agent
distinct, per the finalized 5-agent architecture (Contract Analyst,
Legal/Risk, Business/Finance, Negotiation, Red-Team).

**Consequences:** More prompts and more agent calls to build and wire,
but it enables a genuinely interesting demo: two independent agents
looking at the same evidence and disagreeing. That disagreement path
itself is deferred (ADR-004), but keeping the agents separate is what
makes it buildable later without a re-architecture.

---

## ADR-004: Defer Legal-vs-Risk disagreement escalation to a stretch goal

**Status:** Accepted

**Context:** With Legal/Risk and Business/Finance kept separate (ADR-003),
they could disagree on a material point. Building a full escalation path
for that disagreement (detection, human-review UI, resolution state) is
valuable but not required for the core loop to demonstrate the harness
thesis.

**Decision:** Core build does not implement disagreement detection or
escalation. It is the first item under stretch goals, to attempt only
after the core state machine (Section 6 of architecture.md) works
end-to-end.

**Consequences:** The demo's core path never showcases agent
disagreement unless there is time left over. This is an acceptable
trade for a 4-hour build; the harness's most important behaviors
(policy gate blocking, evidence grounding, contradiction handling) do
not depend on it.

---

## ADR-005: Defer SQLite persistence to a stretch goal

**Status:** Accepted

**Context:** The original architecture draft treated SQLite as core
persistence for negotiation state, contract metadata, and audit events.
For a single demo run inside one Streamlit session, an in-memory Python
dict carries the same information with far less setup and no schema
migrations to get right under time pressure.

**Decision:** Core build uses an in-memory dict as the state store.
SQLite persistence (durable across restarts, queryable audit history) is
a stretch goal, attempted only if the core loop and edge cases are done
with time left over.

**Consequences:** State does not survive a process restart during the
demo. That is fine for a live walkthrough; it would not be fine for a
real deployment, which is explicitly out of scope for this build.

---

## ADR-006: 0.6 confidence threshold for evidence

**Status:** Accepted

**Context:** The Contract Analyst attaches a confidence score to every
extracted fact. The harness needs a concrete, deterministic cutoff below
which a fact cannot be treated as usable evidence by the Negotiation
Agent, per edge case 2 in the finalized scope.

**Decision:** Facts with `confidence < 0.6` are blocked from use in
negotiation planning and flagged in the audit log as "low-confidence -
not used," rather than being silently included or silently dropped. The
comparison is a plain Python `if` check in the policy engine, never an
LLM judgment call (see [claude.md](claude.md)).

**Consequences:** 0.6 is a starting heuristic, not a tuned value - there
was no labeled data to calibrate it against in a 4-hour build. It should
be treated as a config constant, easy to revisit, not a load-bearing
research result.

---

## ADR-007: Contradiction tie-break rule

**Status:** Accepted

**Context:** A vendor contract can contain two clauses addressing the
same term with different values (for example, Section 4.2 capping
escalation at 5% while Appendix B allows up to 15% at renewal). The
harness must not silently pick one, but it also cannot halt the entire
negotiation every time this happens.

**Decision:** On detecting a contradiction, the policy engine
deterministically resolves it for negotiation-planning purposes by
choosing the more conservative, company-favorable value (the lower cap,
the stricter limit), records both source clauses and the chosen value,
and flags the conflict as requiring human sign-off before the final
recommendation is treated as final.

**Consequences:** The negotiation agent always has a usable number to
plan against, so the state machine does not stall. The trade-off is
that "more conservative" is a simplification: it is unambiguous for
numeric caps (lower escalation, shorter termination, higher liability
floor) but would need per-clause-type rules for anything non-numeric.
The core build only needs to handle the numeric case in the demo
contract.

---

## ADR-008: Single policy gate; red-team feeds it rather than its own branch

**Status:** Accepted

**Context:** An earlier architecture draft had two separate policy-gate
checkpoints (one before red-team review, one after), each with its own
pass/fail branch. The finalized state machine given for this build
specifies one linear chain: `RED_TEAM_REVIEW -> POLICY_GATE -> (PASS:
FINAL | FAIL: REPLAN to NEGOTIATION_PLANNING)`.

**Decision:** Collapse to a single policy gate, positioned after
red-team review. Red-team findings that amount to a hard-policy issue
become one of the reasons the single gate fails. Softer, qualitative
red-team concerns are attached to the audit trail regardless of the
gate's outcome, so they are visible even on a pass.

**Consequences:** Simpler graph, one replan target, one failure path to
implement and test - well suited to a 4-hour build. The cost is that a
red-team concern that is not a hard-policy violation cannot, by itself,
force a replan in the core build; it can only be surfaced for human
attention. That is an acceptable simplification for the core scope.

---

## ADR-009: Comparison mode (traditional single-LLM baseline) is the first stretch goal

**Status:** Accepted

**Context:** Of the three stretch goals identified for this build
(Legal-vs-Risk disagreement escalation, SQLite persistence, and a
side-by-side traditional-LLM comparison mode), the comparison mode has
the highest demo value: it makes the harness's value visible in one
screen, showing a naive workflow accept an out-of-policy proposal next
to Warden blocking it.

**Decision:** If the core loop and edge cases are complete with time
left over, build the comparison mode before the other two stretch goals.

**Consequences:** Legal-vs-Risk disagreement escalation and SQLite
persistence may not get built at all in a 4-hour window. That is an
accepted, explicit prioritization, not an oversight.
