"""Env-driven config: the OpenAI model constant and a tiny .env loader.

No python-dotenv dependency - not in the approved stack (claude.md) -
so this file reads .env itself, a few lines, rather than adding one.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _load_dotenv_if_present(path: Path = _ENV_PATH) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv_if_present()

# The one place the model name lives (claude.md) - never hardcoded in agent logic.
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)

# The one place every agent reads its API key from - explicit, not a bare
# OpenAI() relying on os.environ having been populated as a side effect of
# this module happening to be imported first by something else.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
