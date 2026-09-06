# WinWin — Decisions Log (ADR-style)

Each entry: Status, Context, Decision, Consequences. Numbered
chronologically; do not renumber or delete old entries even if later ones
supersede them — mark them superseded instead.

---

## ADR-001: Working project name is "WinWin"

**Status:** Accepted

**Context:** The repo was seeded with docs drafted under the name
"ContractGuard." The team's working title going into the build is
"WinWin." The GitHub repo directory itself is named `-michelin-` (a
placeholder from repo creation) and has not been renamed.

**Decision:** Use "WinWin" as the product name in all docs and, once code
exists, in the app UI and package names. Leave the GitHub repo directory
name (`-michelin-`) alone for now — renaming a GitHub repo mid-hackathon
is a distraction, not a blocker. Rename it later if a different name is
picked.

**Consequences:** Older references to "ContractGuard" in commit history
or early drafts are historical and not the current name. Anyone joining
the repo should treat "WinWin" as authoritative going forward.

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
fewer dependencies. If WinWin ever needs a non-Streamlit client, an API
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
to WinWin blocking it.

**Decision:** If the core loop and edge cases are complete with time
left over, build the comparison mode before the other two stretch goals.

**Consequences:** Legal-vs-Risk disagreement escalation and SQLite
persistence may not get built at all in a 4-hour window. That is an
accepted, explicit prioritization, not an oversight.

---

## ADR-010: Switch LLM provider from Gemini to OpenAI

**Status:** Accepted

**Context:** Earlier docs specified the Gemini API as the LLM provider.
The team has an OpenAI API key available and ready to use, and no
Gemini key in hand, which matters more under a 4-hour time limit than
any difference in model quality between the two.

**Decision:** Use the OpenAI API (`openai` Python package) everywhere an
LLM call is needed, in place of Gemini. The model name is not hardcoded
in agent logic — it lives in a single config constant, defaulting to
`gpt-4o-mini` and overridable via the `OPENAI_MODEL` environment
variable, so it can be swapped (e.g. to a larger model for the demo, or
back to something cheaper for iteration) without touching agent code.
The API key is read from `OPENAI_API_KEY` via a `.env` file, following
`.env.example`; `.env` stays out of version control (already covered by
`.gitignore`).

**Consequences:** `requirements.txt` now pins `openai` instead of the
Gemini SDK package. All prior references to Gemini in architecture.md
and claude.md are updated to OpenAI. No agent has been written yet, so
this switch costs nothing beyond doc and dependency updates — if it had
come after agent code existed, every agent's LLM-call wrapper would have
needed rewriting too.

---

## ADR-011: value normalization happens in the harness, at comparison time

**Status:** Accepted

**Context:** The Contract Analyst agent (built next) will emit exactly
the value shapes a real contract produces: numbers with a unit attached
(8, "percent"), duration text ("Net 30", "180 days"), and free text
(data ownership). The gate needs a defined comparison strategy per
clause type, not a bare float/str compare, before that agent exists.

**Decision:** Each `PolicyRule` gets an `expected_unit` field.
`"days"` tells the gate to parse the raw value (str or number) into an
integer day count via `parse_duration_days()` before comparing;
anything else with `expected_unit` set (e.g. `"percent"`) triggers a
unit-match check against the Clause's own `unit` field, not just a
magnitude comparison. Categorical rules (data ownership) leave
`expected_unit` unset and use `ComparisonDirection.EQUALS`. Parsing and
unit-checking happen in `harness/policy_gate.py` at comparison time,
not on the `Clause` schema or at extraction time — `Clause.vendor_value`
keeps whatever raw shape the extractor produced. An unparseable
duration or a unit mismatch resolves to `CANNOT_VERIFY`, never a crash
or a silent wrong-unit comparison.

**Consequences:** The Contract Analyst can emit values in whatever
literal form the contract uses, and the gate remains the single place
that decides how to compare them. The trade-off: normalization logic
now lives in `evaluate_rule`'s call path rather than being visible on
the schema, so anyone adding a new duration- or unit-bearing clause
type needs to remember to set `expected_unit` on its `PolicyRule`, not
just add the clause_type.

---

## ADR-012: Pin requirements.txt to exact versions

**Status:** Accepted

**Context:** A cross-platform audit found requirements.txt using
floor-only version constraints (`>=X.Y`) for every dependency, with no
upper bound. That leaves `pip install` free to resolve whatever the
newest release happens to be at install time, on whichever OS someone
is installing on - untested against this codebase.

**Decision:** Pin every dependency to the exact version already
confirmed working end to end in this environment (full pytest suite
plus live pipeline runs against real PDFs): `langgraph==1.2.11`,
`openai==3.8.0`, `streamlit==1.63.0`, `pymupdf==1.28.2`,
`pydantic==2.13.5`, `pandas==3.0.5`.

**Consequences:** A fresh install reproduces a known-good set of
versions instead of gambling on whatever is newest, which is what
actually protects against a platform-specific wheel or build issue
showing up only on someone else's OS. The cost: dependencies now need
a deliberate bump (and a re-test) to move forward, rather than picking
up patch releases automatically - the right trade-off for a hackathon
build where "it works on my machine" needs to also work on a judge's.

---

## ADR-013: Second rename, "Warden" to "WinWin"

**Status:** Accepted

**Context:** ADR-001 settled on "Warden" as the working name, and the
codebase (agent prompts, the Streamlit UI, and all of these docs) used it
throughout the core build. Ahead of the live demo, the team settled on
"WinWin" as the final name instead.

**Decision:** Renamed every occurrence of "Warden" to "WinWin" across the
codebase and docs (agent system prompts, UI strings, architecture.md,
decisions.md, failures.md, methodology.md, claude.md,
problem_statement.md) via a direct text replace - including inside
ADR-001 and elsewhere in this log. README.md was intentionally left
untouched in this pass, handled separately by the team. No files were
renamed; nothing had "warden" in a filename.

**Consequences:** This log's own entries (ADR-001 in particular) now read
as if "WinWin" was always the name, which is not literally true - this
entry is what preserves the real history for anyone reading later: the
project was named **ContractGuard** (pre-build draft) -> **Warden**
(from the repo's first commit through the core build) -> **WinWin**
(final, pre-demo, commit `3258c96`). Git history remains the authoritative record
of exactly when each name was in effect; do not "correct" ADR-001's text
back to "Warden" later under the mistaken impression it was left stale by
accident.

---

## ADR-014: Policy-extraction default-fallback design

**Status:** Accepted

**Context:** `agents/policy_analyst.py` extracts a company's negotiation
policy from an uploaded policy PDF (an optional alternative to the
shipped `data/policy_config.json` default). Not every rule type is
confidently or explicitly stated in a given policy document, and here a
wrong hard limit is worse than no extraction at all - it feeds directly
into the same `POLICY_GATE` that decides whether a negotiation move is
allowed to proceed, for every rule in the run.

**Decision:** The LLM extracts only the numeric `target_value` /
`hard_limit_value` pair, a `found` flag, and a confidence score per rule
type. The structural fields - `direction`, `expected_unit`,
`reference_clause_type`, `description` - always come from the shipped
`data/policy_config.json` template and are never re-derived by the model;
they are domain facts (e.g. "lower escalation is better") that do not
vary per company. Below `POLICY_RULE_CONFIDENCE_THRESHOLD = 0.7`, or if a
rule type is not found in the document at all, that rule falls back to
the config default rather than guessing, and is tagged
`PolicyRuleSource.DEFAULT_FALLBACK` (vs. `EXTRACTED`) so callers can tell
the two apart.

**Consequences:** The Streamlit policy-review table (`app/main.py`)
surfaces this distinction directly to the user before they confirm and
run a negotiation - a low-confidence or missing extraction is visible,
never silently substituted. The 0.7 threshold is deliberately stricter
than the evidence-extraction threshold (0.6, ADR-006): a wrong policy
rule taints every downstream negotiation decision in the run, not just
one clause's evaluation.

---

## ADR-015: Fix the two bugs blocking the FINAL approval path

**Status:** Accepted

**Context:** A pre-demo check found that all five original sample PDFs
escalated to `HUMAN_REVIEW` after exhausting every replan. Before
accepting "the sample contracts are violation-heavy by design" as the
explanation, a deliberately fully policy-compliant contract (every clause
at or better than `data/policy_config.json`'s target, no contradictions)
was run through the real graph to check whether `FINAL` is reachable at
all. It was not: the proposal correctly needed no changes, both the
Legal/Risk and Business/Finance reviews correctly returned `ACCEPT`, and
the run still exhausted all 3 replans. Two separate, real bugs were
found:

1. `agents/red_team.py`'s system prompt told the model to "actively look
   for reasons to reject," with no counter-instruction for the case
   where none exist. It kept inventing speculative, non-evidence-grounded
   objections ("cumulative financial risk," hypothetical future
   scenarios) even with every policy check PASS and both other reviewers
   at ACCEPT.
2. `harness/grounding_check.py`'s rationale number-extraction regex did
   not handle comma-grouped numbers (`"1,000,000"` tokenized as `"1"`,
   `"000"`, `"000"`, none of which equals the cited clause's real value
   `1000000.0`), so any proposal citing a large clause value the ordinary
   way got a false `GROUNDING_FAILED`, crashing the pipeline with
   `NegotiationAgentError` instead of proceeding.

**Decision:** Fixed both narrowly, without touching the hard-gate logic
in `harness/graph.py` (`red_team_rejected` still forces `hard_fail` -
that block on a genuine `REJECT` is correct and untouched). Rewrote the
Red-Team prompt with an explicit decision rule: a `REJECT` verdict must
cite a specific item from the evidence given (a policy result, a named
review concern, or a contradiction in the proposal itself); absent that,
the verdict must be `ACCEPT`. Fixed the grounding-check regex to match a
comma-grouped number as one token before falling back to plain digits.

**Consequences:** A genuinely compliant contract now reliably reaches
`FINAL` with 0 replans (verified live, repeatedly, via
`tests/manual_test_clean_contract.py` and the `clean_pass_demo.pdf` PDF
round-trip in `tests/manual_test_real_pdfs.py`) - the harness can approve
a good deal, not just catch bad ones. One residual, milder issue was
observed and left as-is rather than chased further under time pressure:
the Contract Analyst occasionally emits a redundant duplicate
`not_specified` entry alongside a real one for the same `clause_type`,
which can confuse Business/Finance into a spurious `FLAG` even though
`POLICY_CHECK` itself correctly filters the duplicate out and still shows
PASS. This is LLM extraction non-determinism, not a structural defect -
worth another look if it recurs often, but out of scope for this pass.

---

## ADR-016: Frontend redesign approach

**Status:** Accepted

**Context:** The Streamlit UI's original styling used a generic
default-blue theme with heavy emoji use for section labels and buttons,
and had no consistent visual language for the five `CheckStatus` values
(`PASS`, `BLOCKED`, `CONFLICTING`, `CANNOT_VERIFY`, `LOW_CONFIDENCE`) or
the `FINAL` vs. `HUMAN_REVIEW` terminal states - all of which are
central to what the harness actually does and deserved to read as
intentional, not decorative, ahead of a live demo.

**Decision:** Adopted one neutral palette (slate/charcoal text, an
off-white ground, a single muted steel-blue accent used consistently for
buttons, the active tab, and metric values) plus one fixed status-color
system (green for PASS/ACCEPT, red for BLOCKED/REJECT, amber for
CONFLICTING/FLAG, gray for CANNOT_VERIFY, navy for HUMAN_REVIEW) applied
everywhere those states appear. No new dependency was added: table cell
coloring uses pandas' own `Styler` (already an approved dependency, ADR
stack list in claude.md), not a new charting/UI library. Emoji were
removed in favor of the badge system and typography for signaling state.
`FINAL` and `HUMAN_REVIEW` get visually distinct banners so the latter
reads as an explicit flagged stop, not an error.

**Consequences:** Purely presentational - no session-state keys,
function calls, or control flow in `app/main.py` changed; verified live
that `streamlit run app/main.py` still starts cleanly and the full pytest
suite still passes. The Extracted Clauses table's Confidence column is
now colored against the project's real 0.6 threshold (ADR-006), so the
UI visualizes actual harness logic rather than being purely decorative.
