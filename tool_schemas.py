"""ZONE 1 — Tool schemas.  ★ WRITE THIS ★

The list of tools your LLM may call, in OpenAI **Chat Completions** shape:

    {"type": "function",
     "function": {"name": ..., "description": ..., "parameters": <JSON Schema>}}

This is the standard OpenAI Chat Completions tool shape.

Two rules the startup check enforces (tools.validate_tool_registry):
  1. Every `name` here has a matching function in tools.py's TOOL_REGISTRY.
  2. The `parameters` here match that function's signature — each schema
     property is a keyword arg of the function; required properties may or may
     not have a default; OPTIONAL properties must have a default.

So the schema and the Python signature are two views of one thing. (If you ever
want this to be impossible to get wrong, generate these schemas FROM the typed
functions instead — see CLAUDE.md "Closing the gap further".)

These three tools are literature-search lookups against free, no-key public
APIs (PubMed, Semantic Scholar, arXiv). They only ever return what the upstream
API actually returned (title/authors/year/abstract/URL) or an explicit
``{"ok": False, "error": ...}`` — there is no path by which the model can be
handed a fabricated citation from a tool result.
"""
from __future__ import annotations

from typing import Any

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_pubmed",
            "description": (
                "Search PubMed (biomedical/clinical/life-sciences literature) for papers "
                "matching a query. Returns title, authors, year, journal, abstract, and a "
                "PubMed URL for each match. Best for medical, clinical, biological, and "
                "public-health questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search terms, e.g. 'metformin cancer risk'.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max number of papers to return (1-10). Defaults to 5.",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_semantic_scholar",
            "description": (
                "Search Semantic Scholar (broad, cross-discipline academic search covering "
                "CS, engineering, social science, medicine, and more) for papers matching a "
                "query. Returns title, authors, year, venue, abstract, and a URL for each "
                "match. Good general-purpose fallback when a topic isn't clearly biomedical "
                "or a physics/CS preprint."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search terms, e.g. 'large language model evaluation'.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max number of papers to return (1-10). Defaults to 5.",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_arxiv",
            "description": (
                "Search arXiv (physics, math, CS, quantitative biology/finance preprints) for "
                "papers matching a query. Returns title, authors, year, abstract, and a URL "
                "for each match. Best for preprint / methods-heavy technical questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search terms, e.g. 'diffusion models image generation'.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max number of papers to return (1-10). Defaults to 5.",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
]
