# Warden

Warden lets AI negotiate vendor contracts, but puts every AI-generated
negotiation move through an enforceable policy, evidence, and
independent-review harness before allowing it to proceed.

## Status

Docs and repo scaffold only — no business logic yet (this is commit #1 of
the build). See [architecture.md](architecture.md) for the finalized
design, [decisions.md](decisions.md) for the reasoning behind it, and
[methodology.md](methodology.md) for build order.

Working title: **Warden**. The repo directory name (`-michelin-`) predates
the name and will be renamed later — this does not block development.

## Setup

Placeholder — to be filled in once code exists.

```
# 1. clone and enter the repo
git clone <repo-url>
cd -michelin-

# 2. create a virtualenv and install dependencies
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt

# 3. set your OpenAI API key
copy .env.example .env
# edit .env and set OPENAI_API_KEY=...

# 4. run the app
streamlit run app/main.py    # not yet created
```

## Project docs

- [problem_statement.md](problem_statement.md) — the problem and why a harness is needed
- [architecture.md](architecture.md) — agents, state machine, policy gate, stack
- [decisions.md](decisions.md) — ADR log
- [failures.md](failures.md) — failure modes this system is designed to catch
- [methodology.md](methodology.md) — build order and engineering rules
- [claude.md](claude.md) — working notes for AI-assisted development on this repo
