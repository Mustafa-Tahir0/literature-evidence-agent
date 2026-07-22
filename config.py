"""Shared configuration & constants.

SUPPORT FILE — you normally only edit the DEFAULT_* values below.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- Identity -------------------------------------------------------------
AGENT_NAME = "Literature Evidence Assistant"     # ★ set to your agent's name

# --- Networking -----------------------------------------------------------
DEFAULT_HOST = "0.0.0.0"          # bind address (listen on all interfaces)
DEFAULT_PORT = 9110               # pick a free port

# --- LLM ------------------------------------------------------------------
DEFAULT_MODEL = "gpt-4o-mini"     # hosted model name, or your vLLM --served-model-name
# 6, not the template default of 4: a typical query calls up to 3 search tools
# (pubmed + semantic_scholar + arxiv) before the model can synthesize a final
# answer, and 4 leaves no margin for a retried/refined search.
MAX_TOOL_STEPS = 6                # cap on tool-call loop iterations

# --- Paths ----------------------------------------------------------------
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CARD_PATH = PACKAGE_DIR / "agent.card.json"


# --- Env readers (so deployment can override without code edits) ----------
def env_model() -> str:
    return os.getenv("AGENT_MODEL", DEFAULT_MODEL)


def env_host() -> str:
    return os.getenv("AGENT_A2A_HOST", DEFAULT_HOST)


def env_port() -> int:
    return int(os.getenv("AGENT_A2A_PORT", str(DEFAULT_PORT)))


def env_advertise_url() -> str | None:
    return os.getenv("AGENT_A2A_URL")
