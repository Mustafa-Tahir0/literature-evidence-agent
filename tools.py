"""ZONE 4 — Tool dispatch + tool bodies.  ★ WRITE THE BODIES ★ (dispatch is copy)

- Tool BODIES: three literature-search lookups against free, no-key public APIs
  (PubMed E-utilities, Semantic Scholar Graph API, arXiv). Each takes keyword
  args named exactly like its schema `properties` and returns a JSON-able dict.
  Every result is either data the upstream API actually returned, or an
  explicit ``{"ok": False, "error": ...}`` — there is no path that hands the
  model a fabricated paper.
- TOOL_REGISTRY: the {name: function} map the LLM loop dispatches over.
- validate_tool_registry(): a startup alignment check — fails fast if a schema
  and its function disagree, instead of failing silently at runtime.

Trust/safety note: a tool returning ``ok: True, count: 0`` means the search
genuinely ran and found nothing (real absence of evidence). A tool returning
``ok: False`` means the search itself failed (network error, rate limit) —
that is NOT evidence of absence, and the system prompt (prompt.py) instructs
the model to keep that distinction visible to the user rather than treating a
failed search as "no papers exist".
"""
from __future__ import annotations

import inspect
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Callable

from .tool_schemas import TOOL_SCHEMAS

_HTTP_TIMEOUT_S = 10
_USER_AGENT = "agent-skeleton-literature-agent/0.1 (WashU DTRC hackathon; contact via repo)"


def _clamp(n: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _http_get(url: str, extra_headers: dict[str, str] | None = None) -> bytes:
    headers = {"User-Agent": _USER_AGENT, "Accept": "*/*", **(extra_headers or {})}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:
        return resp.read()


def _http_get_json(url: str, extra_headers: dict[str, str] | None = None) -> Any:
    return json.loads(_http_get(url, extra_headers).decode("utf-8"))


# --- search_pubmed ---------------------------------------------------------

_PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_PUBMED_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def _pubmed_ids(query: str, max_results: int) -> list[str]:
    params = {"db": "pubmed", "term": query, "retmax": max_results, "retmode": "json"}
    url = f"{_PUBMED_ESEARCH}?{urllib.parse.urlencode(params)}"
    data = _http_get_json(url)
    return list((data.get("esearchresult") or {}).get("idlist") or [])


def _pubmed_text(elem: ET.Element | None, path: str) -> str:
    found = elem.find(path) if elem is not None else None
    return "".join(found.itertext()).strip() if found is not None else ""


def _pubmed_article(article: ET.Element) -> dict[str, Any]:
    pmid = _pubmed_text(article, ".//MedlineCitation/PMID")
    title = _pubmed_text(article, ".//Article/ArticleTitle")
    journal = _pubmed_text(article, ".//Article/Journal/Title")

    abstract_parts = [
        "".join(node.itertext()).strip()
        for node in article.findall(".//Article/Abstract/AbstractText")
    ]
    abstract = " ".join(p for p in abstract_parts if p)

    year = _pubmed_text(article, ".//Article/Journal/JournalIssue/PubDate/Year")
    if not year:
        medline_date = _pubmed_text(article, ".//Article/Journal/JournalIssue/PubDate/MedlineDate")
        year = medline_date[:4] if medline_date[:4].isdigit() else ""

    authors: list[str] = []
    for author in article.findall(".//Article/AuthorList/Author"):
        last = _pubmed_text(author, "LastName")
        initials = _pubmed_text(author, "Initials")
        name = " ".join(p for p in (last, initials) if p)
        if name:
            authors.append(name)

    doi = ""
    for eid in article.findall(".//ArticleIdList/ArticleId"):
        if eid.get("IdType") == "doi":
            doi = (eid.text or "").strip()
            break

    return {
        "pmid": pmid,
        "title": title or "(no title)",
        "authors": authors[:6],
        "year": year or None,
        "journal": journal or "",
        "abstract": abstract or "",
        "doi": doi or None,
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
    }


def search_pubmed(*, query: str, max_results: int = 5) -> dict[str, Any]:
    n = _clamp(max_results, 1, 10, 5)
    try:
        ids = _pubmed_ids(query, n)
        if not ids:
            return {"ok": True, "source": "pubmed", "query": query, "count": 0, "papers": []}
        params = {"db": "pubmed", "id": ",".join(ids), "rettype": "abstract", "retmode": "xml"}
        url = f"{_PUBMED_EFETCH}?{urllib.parse.urlencode(params)}"
        root = ET.fromstring(_http_get(url))
        papers = [_pubmed_article(a) for a in root.findall(".//PubmedArticle")]
        return {"ok": True, "source": "pubmed", "query": query, "count": len(papers), "papers": papers}
    except Exception as exc:  # network/parsing failure is a tool error, not silence
        return {"ok": False, "source": "pubmed", "query": query, "error": f"{type(exc).__name__}: {exc}"}


# --- search_semantic_scholar ------------------------------------------------

_S2_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"


def search_semantic_scholar(*, query: str, max_results: int = 5) -> dict[str, Any]:
    n = _clamp(max_results, 1, 10, 5)
    try:
        params = {
            "query": query,
            "limit": n,
            "fields": "title,abstract,year,authors,venue,externalIds,url",
        }
        url = f"{_S2_SEARCH}?{urllib.parse.urlencode(params)}"
        # Anonymous requests share a small public rate-limit pool and 429 easily.
        # A free key (https://www.semanticscholar.org/product/api#api-key) raises
        # that limit substantially; read it from the environment only, never hard-code it.
        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        headers = {"x-api-key": api_key} if api_key else None
        data = _http_get_json(url, headers)
        papers = []
        for item in data.get("data") or []:
            authors = [a.get("name") for a in (item.get("authors") or []) if a.get("name")]
            paper_id = item.get("paperId")
            papers.append(
                {
                    "title": item.get("title") or "(no title)",
                    "authors": authors[:6],
                    "year": item.get("year"),
                    "venue": item.get("venue") or "",
                    "abstract": item.get("abstract") or "",
                    "doi": (item.get("externalIds") or {}).get("DOI"),
                    "url": item.get("url") or (f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else ""),
                }
            )
        return {"ok": True, "source": "semantic_scholar", "query": query, "count": len(papers), "papers": papers}
    except Exception as exc:
        return {"ok": False, "source": "semantic_scholar", "query": query, "error": f"{type(exc).__name__}: {exc}"}


# --- search_arxiv ------------------------------------------------------------

_ARXIV_API = "http://export.arxiv.org/api/query"
_ATOM_NS = "{http://www.w3.org/2005/Atom}"


def search_arxiv(*, query: str, max_results: int = 5) -> dict[str, Any]:
    n = _clamp(max_results, 1, 10, 5)
    try:
        params = {"search_query": f"all:{query}", "start": 0, "max_results": n}
        url = f"{_ARXIV_API}?{urllib.parse.urlencode(params)}"
        root = ET.fromstring(_http_get(url))
        papers = []
        for entry in root.findall(f"{_ATOM_NS}entry"):
            title = (entry.findtext(f"{_ATOM_NS}title") or "").strip()
            summary = (entry.findtext(f"{_ATOM_NS}summary") or "").strip()
            published = (entry.findtext(f"{_ATOM_NS}published") or "").strip()
            entry_id = (entry.findtext(f"{_ATOM_NS}id") or "").strip()
            authors = [
                (a.findtext(f"{_ATOM_NS}name") or "").strip()
                for a in entry.findall(f"{_ATOM_NS}author")
            ]
            papers.append(
                {
                    "title": title or "(no title)",
                    "authors": [a for a in authors if a][:6],
                    "year": published[:4] if published[:4].isdigit() else None,
                    "abstract": summary,
                    "url": entry_id,
                }
            )
        return {"ok": True, "source": "arxiv", "query": query, "count": len(papers), "papers": papers}
    except Exception as exc:
        return {"ok": False, "source": "arxiv", "query": query, "error": f"{type(exc).__name__}: {exc}"}


# --- Registry (one entry per tool)  ★ EDIT ★ -----------------------------

TOOL_REGISTRY: dict[str, Callable[..., dict[str, Any]]] = {
    "search_pubmed": search_pubmed,
    "search_semantic_scholar": search_semantic_scholar,
    "search_arxiv": search_arxiv,
}


# --- The alignment check -----------------

def validate_tool_registry(
    schemas: list[dict[str, Any]] | None = None,
    registry: dict[str, Callable[..., dict[str, Any]]] | None = None,
) -> None:
    """Fail fast if schemas and functions disagree. Called by serve.create_app.

    For every tool it checks that:
      * the schema `name` has a function (and every function has a schema);
      * every schema property is a keyword parameter of the function;
      * every OPTIONAL property's parameter carries a default (so the model may
        omit it without a TypeError at call time);
      * the function has no required parameter that the schema does not declare.
    A function may declare **kwargs to opt out of the strict parameter checks.

    Raises ValueError listing ALL problems; returns None when everything aligns.
    """
    schemas = TOOL_SCHEMAS if schemas is None else schemas
    registry = TOOL_REGISTRY if registry is None else registry

    problems: list[str] = []
    schema_names: list[str] = []

    for schema in schemas:
        fn_spec = schema.get("function") or {}
        name = str(fn_spec.get("name") or "")
        if not name:
            problems.append("a schema entry is missing function.name")
            continue
        schema_names.append(name)

        params = fn_spec.get("parameters") or {}
        props = set((params.get("properties") or {}).keys())
        required = set(params.get("required") or [])

        fn = registry.get(name)
        if fn is None:
            problems.append(f"[{name}] schema has no function in TOOL_REGISTRY")
            continue

        sig = inspect.signature(fn)
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            continue  # function opts out of strict checks via **kwargs

        fn_params = {
            n: p
            for n, p in sig.parameters.items()
            if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        }
        fn_required = {n for n, p in fn_params.items() if p.default is inspect.Parameter.empty}

        # schema -> function
        for prop in sorted(props):
            if prop not in fn_params:
                problems.append(f"[{name}] schema property '{prop}' is not a parameter of {fn.__name__}()")
        for prop in sorted(props - required):
            if prop in fn_params and fn_params[prop].default is inspect.Parameter.empty:
                problems.append(f"[{name}] optional property '{prop}' must have a default in {fn.__name__}()")
        # function -> schema
        for pname in sorted(fn_params):
            if pname not in props:
                problems.append(f"[{name}] {fn.__name__}() parameter '{pname}' is not declared in the schema")
        for pname in sorted(fn_required):
            if pname not in required:
                problems.append(f"[{name}] {fn.__name__}() requires '{pname}' but the schema does not mark it required")

    for name in registry:
        if name not in schema_names:
            problems.append(f"[{name}] function in TOOL_REGISTRY has no schema in TOOL_SCHEMAS")

    if problems:
        raise ValueError("Tool schema/function alignment failed:\n  - " + "\n  - ".join(problems))
