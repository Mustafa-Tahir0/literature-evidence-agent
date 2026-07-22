"""ZONE 2 — System prompt + result normalization.  ★ WRITE THIS ★

- SYSTEM_PROMPT: the instructions that define the Literature Evidence Assistant's
  behavior and the exact output contract expected from the model.
- normalize_result(): turn the model's final text into the STABLE structured dict
  the agent returns.

Why a stable shape matters: the planner reads the structured DataPart artifact
this agent emits, so downstream callers depend on these keys always existing.
"""
from __future__ import annotations

import json
from typing import Any

SYSTEM_PROMPT = (
    "You are the Literature Evidence Assistant, a research aide for WashU faculty, "
    "graduate students, and other researchers doing a literature review or checking "
    "a claim before it goes into a paper, grant, or protocol.\n\n"
    "You have three search tools: search_pubmed (biomedical/clinical), "
    "search_semantic_scholar (broad cross-discipline), and search_arxiv "
    "(physics/CS/math/quantitative preprints). For any research question or claim:\n"
    "1. Decide which tool(s) fit the topic and call them (you may call more than one "
    "source when a topic could plausibly appear in either — e.g. call both "
    "search_pubmed and search_semantic_scholar for a biomedical ML question).\n"
    "2. Base your answer ONLY on the papers those tools actually returned. Never "
    "invent a paper, author, year, DOI, or URL — every citation in your answer must "
    "correspond to an entry in a tool result.\n"
    "3. A tool result with ok:true and count:0 means the search genuinely ran and "
    "found nothing — say evidence is absent or sparse. A tool result with ok:false "
    "means the search ITSELF failed (network error, rate limit) — that is NOT "
    "evidence of absence; say the source could not be searched rather than implying "
    "no literature exists.\n"
    "4. If the retrieved papers disagree with each other, surface the disagreement "
    "explicitly rather than silently picking a side.\n"
    "5. Never overclaim: an abstract is not the full paper, and a handful of search "
    "hits is not a systematic review. Say so when it's relevant.\n\n"
    "Return ONLY valid JSON with these keys, and no prose outside the JSON object:\n"
    "  answer (string): the evidence synthesis in plain language, citing sources "
    "inline as (Author, Year).\n"
    "  sources (array of objects): one entry per paper you cited, each with "
    "title, authors, year, url, and source (pubmed/semantic_scholar/arxiv) — copied "
    "directly from the tool results, never invented.\n"
    "  confidence (string): one of 'strong', 'mixed', 'weak', or 'insufficient', "
    "reflecting how well the retrieved evidence answers the question.\n"
    "  caveats (array of strings): limitations, contradictions, failed searches, or "
    "reasons to treat the answer cautiously. Empty array only if there truly are none.\n"
)


def normalize_result(raw_text: str, tool_log: list[dict[str, Any]]) -> dict[str, Any]:
    """Coerce the model's final text into a stable result dict.

    Always returns the same keys so callers can rely on them even if the model
    returns malformed JSON. Falls back to listing every paper actually returned
    by the tools (rather than nothing) if the model's own `sources` list is
    missing or malformed, so a citation never silently disappears.
    """
    data: dict[str, Any] = {}
    text = (raw_text or "").strip()

    # Tolerate ```json fences around the JSON.
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            data = parsed
    except (ValueError, TypeError):
        data = {}

    answer = str(data.get("answer") or raw_text or "").strip() or "(no answer produced)"

    sources = data.get("sources")
    if not isinstance(sources, list) or not sources:
        sources = _sources_from_tool_log(tool_log)

    confidence = data.get("confidence")
    if confidence not in ("strong", "mixed", "weak", "insufficient"):
        confidence = "insufficient" if not sources else "weak"

    caveats = data.get("caveats")
    if not isinstance(caveats, list):
        caveats = []
    caveats = [str(c) for c in caveats]
    caveats.extend(_failure_caveats(tool_log))

    tools_used = [str(call.get("name")) for call in tool_log]

    return {
        "answer": answer,
        "sources": sources,
        "confidence": confidence,
        "caveats": caveats,
        "tools_used": tools_used,
        # The executor uses response_text as the human-readable A2A message.
        "response_text": answer,
    }


def _sources_from_tool_log(tool_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for call in tool_log:
        result = call.get("result") or {}
        if not isinstance(result, dict) or not result.get("ok"):
            continue
        for paper in result.get("papers") or []:
            sources.append(
                {
                    "title": paper.get("title"),
                    "authors": paper.get("authors"),
                    "year": paper.get("year"),
                    "url": paper.get("url"),
                    "source": result.get("source"),
                }
            )
    return sources


def _failure_caveats(tool_log: list[dict[str, Any]]) -> list[str]:
    caveats: list[str] = []
    for call in tool_log:
        result = call.get("result") or {}
        if isinstance(result, dict) and result.get("ok") is False:
            caveats.append(
                f"{result.get('source') or call.get('name')} search failed "
                f"({result.get('error') or 'unknown error'}) — this is a missing "
                "search, not evidence that no literature exists."
            )
    return caveats
