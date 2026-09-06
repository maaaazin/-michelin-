# Working notes for AI-assisted development on this repo

These are working notes for whoever (human or AI) is writing code in this
repo, kept separate from the design docs so process/convention questions
do not get lost inside architecture.md or decisions.md.

## Project identity

- Working product name: **Warden**. Repo directory name is `-michelin-`
  (predates the name) - do not let that block anything; see
  [decisions.md](decisions.md) ADR-001.
- Domain: Operations & Compliance. Core idea: an LLM proposes negotiation
  moves, a deterministic harness decides whether each move is allowed to
  proceed.
- Read [problem_statement.md](problem_statement.md),
  [architecture.md](architecture.md), and [decisions.md](decisions.md)
  before writing code that touches the state machine or the policy
  engine - the design choices there (especially the finalized state
  machine and the single-policy-gate decision, ADR-008) are deliberate
  and should not be silently redesigned mid-build.

## The one rule that matters most

**LLM calls are for reasoning and strategy only - never for deciding
whether a number crosses a threshold.**

If you are about to write a prompt that asks the model "is 8% greater
than the 5% limit?" or "does this value violate policy?", stop: that
check belongs in `/harness` as a plain Python comparison, not in a
prompt. See [methodology.md](methodology.md) for the full reasoning.
Concretely:

- Hard-constraint checks (the policy gate) -> plain Python, in
  `/harness`.
- Confidence-threshold checks (the 0.6 cutoff) -> plain Python, in
  `/harness`.
- `NOT_SPECIFIED` handling and contradiction tie-breaks -> plain Python,
  in `/harness`.
- Clause extraction, risk assessment, negotiation strategy, red-team
  critique -> LLM calls, in `/agents`.

## Ask before adding a new dependency

The approved stack is fixed for this build: `langgraph`, the Gemini SDK,
`streamlit`, `pymupdf`, `pydantic` (see `requirements.txt`). Do not add a
new package - including a "just this one small helper library" - without
flagging it to the user first and getting a yes. This includes swapping
in a different Gemini SDK package name than the one already pinned in
`requirements.txt`; if that package changes upstream, flag it rather than
silently switching.

Explicitly out of scope unless the user asks otherwise: FastAPI (ADR-002
covers why), Kubernetes, vector databases, authentication/authorization
frameworks, a microservice split, or a general RAG pipeline (structured
extraction with PyMuPDF + Pydantic is enough for this project's
documents).

## Coding conventions

- Python, type-hinted. Every cross-boundary data structure (agent
  input/output, harness state, policy config) is a Pydantic model in
  `/schemas`, not a bare dict - that is the whole point of "structured
  evidence" in this project.
- Keep the folder boundaries meaningful:
  - `/schemas` - Pydantic models only, no logic.
  - `/harness` - deterministic Python: policy engine, policy gate,
    evidence validation, retry/failure routing, audit logging, the
    LangGraph state machine wiring.
  - `/agents` - LLM-calling code, one module per agent (Contract
    Analyst, Legal/Risk, Business/Finance, Negotiation, Red-Team).
  - `/data` - demo contract(s) and company policy fixtures.
  - `/app` - Streamlit UI, calling the graph directly (no API layer -
    ADR-002).
- An agent module should never import a policy threshold and check it
  itself; it should call into `/harness` and get back a decision.

## Commit convention

Imperative mood, one feature per commit, prefixed by type:

```
feat: add deterministic policy gate engine
feat: add contract analyst agent
fix: correct confidence threshold comparison direction
docs: update architecture for finalized state machine
```

One feature per commit means: do not bundle the policy engine and the
negotiation agent into the same commit just because they were written in
the same sitting. Small, reviewable commits matter more than commit
count in a time-boxed build, because they are what make it possible to
tell later which piece broke.

## Current status

Commit #1 (this one): docs finalized, folder skeleton created, no
business logic yet. Next up per [methodology.md](methodology.md): Pydantic
schemas, then the policy engine.
