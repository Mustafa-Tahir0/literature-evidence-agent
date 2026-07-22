# Literature Evidence Assistant

An A2A agent, built on `agent_skeleton`, that helps a researcher check what the
literature actually says before it goes into a paper, grant, or protocol.

## What research workflow does this improve?

Literature review and evidence-checking: instead of manually searching PubMed,
Semantic Scholar, and arXiv and reading abstracts to see whether a claim is
supported, contradicted, or unstudied, you ask the agent a question and it does
the search, reads what actually came back, and tells you what the evidence
shows — with a link to every paper it cites.

## Who at WashU would benefit?

Faculty investigators, graduate students, postdocs, and clinician-researchers
who are drafting a paper, grant, or protocol and need a fast, honest first pass
at "what does the literature say about X" before committing to a claim or
deciding a deeper systematic search is warranted. It spans biomedical (PubMed),
general/cross-discipline (Semantic Scholar), and technical/preprint (arXiv)
literature, so it's useful outside any one department.

## What does this do that a general chatbot would not?

A general chatbot answers "what does the literature say" from its training
data and will confidently produce plausible-looking papers, authors, and DOIs
that don't exist. This agent instead:

- **Searches live, real sources** (PubMed, Semantic Scholar, arXiv) for every
  answer — it does not answer from memory.
- **Only cites what a tool actually returned.** Every entry in the `sources`
  list is copied from a real API response; there is no code path that lets the
  model hand back a fabricated citation.
- **Distinguishes "no evidence found" from "the search failed."** A tool
  returning `ok: true, count: 0` means it genuinely searched and found
  nothing; `ok: false` means PubMed/Semantic Scholar/arXiv couldn't be reached
  or rate-limited the request. The agent is instructed never to conflate the
  two, and the failure is always surfaced as a `caveat`, not swallowed.
- **Reports a `confidence` level** (`strong` / `mixed` / `weak` /
  `insufficient`) and surfaces disagreement between papers instead of
  silently picking a side.

## What is it designed to handle well?

- "What does the evidence say about `<claim>`?" (e.g. "metformin and cancer risk")
- "Is there research support for `<intervention>` improving `<outcome>`?"
- "Find recent papers on `<technical topic>`" (routes to arXiv/Semantic Scholar)
- "Do studies on `<X>` and `<Y>` agree with each other?" (asks it to look for
  and name contradictions)
- Ambiguous/missing input: an empty or missing prompt gets an explicit
  "please provide a request" response rather than a guess (see
  `executor.py`'s `_requires_input`); a topic with genuinely no hits gets an
  `insufficient`-confidence answer that says so, not an invented one.

It is **not** designed to read full paper text (only titles/abstracts/metadata
from search APIs), replace a systematic review, or serve as compliance/medical
advice — see Limitations below.

## What tools, files, APIs, or other agents does it use?

Three tool calls, all free and keyless, implemented in [`tools.py`](tools.py)
with Python's stdlib `urllib` (no extra HTTP dependency):

| Tool | Backing API | Auth |
|---|---|---|
| `search_pubmed` | [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/) (esearch + efetch) | none |
| `search_semantic_scholar` | [Semantic Scholar Graph API](https://api.semanticscholar.org/api-docs/graph) | none required; optional key via `SEMANTIC_SCHOLAR_API_KEY` raises the anonymous rate limit |
| `search_arxiv` | [arXiv API](https://info.arxiv.org/help/api/index.html) | none |

No files, databases, or other agents are used. The agent itself calls an LLM
through the standard OpenAI Chat Completions shape (`OPENAI_API_KEY` +
optional `OPENAI_BASE_URL` for a self-hosted/vLLM endpoint) — see "If your
agent calls an LLM" below.

## How does it handle uncertainty, privacy, credentials, and limitations?

- **Uncertainty:** every response carries a `confidence` field and a `caveats`
  array (see `prompt.py`'s `normalize_result`) — including automatic caveats
  for any tool call that failed, so a rate-limited or unreachable source is
  never silently treated as "no literature exists."
- **No fabrication:** the system prompt (`prompt.py`) explicitly forbids
  citing anything not present in a tool result; `normalize_result` also
  falls back to the papers the tools actually returned if the model's own
  `sources` list is missing or malformed, so a real citation can't disappear
  and a fake one can't appear.
- **Privacy/credentials:** the agent only ever sends search *queries* (text
  the user typed) to public literature APIs — no user data, files, or
  credentials are involved. The only secret this agent needs is
  `OPENAI_API_KEY` for its own LLM calls (any placeholder value works against
  a local vLLM endpoint); `SEMANTIC_SCHOLAR_API_KEY` is optional. Neither is
  committed to this repo — see `.env.example` and set them via environment
  variables at deploy time.
- **Limitations:** searches cover titles/abstracts/metadata only, not full
  paper text; a handful of search hits is not a systematic review; PubMed
  favors biomedical topics and can miss purely technical/CS literature (and
  vice versa for arXiv) — the agent is prompted to pick sources by topic, but
  for a niche cross-domain question it may still miss a relevant source not
  covered by any of the three. Free-tier upstream APIs can rate-limit or
  time out, which is surfaced as a caveat rather than a false negative.

## Example input / output

**Input** (`prompt`): `"What does the evidence say about metformin and cancer risk?"`

**Output** (the structured `DataPart`, abbreviated):

```json
{
  "answer": "Several recent studies explore repurposing metformin in oncology... (Wenqian, 2026)...",
  "sources": [
    {"title": "Network toxicology-driven repurposing of metformin for hepatocellular carcinoma", "authors": ["Wenqian G"], "year": "2026", "url": "https://pubmed.ncbi.nlm.nih.gov/42470472/", "source": "pubmed"}
  ],
  "confidence": "mixed",
  "caveats": ["semantic_scholar search failed (HTTP 429) — this is a missing search, not evidence that no literature exists."],
  "tools_used": ["search_pubmed", "search_semantic_scholar"]
}
```

The same `answer` text is also sent as the human-readable A2A message.

*(Verified end-to-end: `serve check` passes, all 40 unit tests pass, and a live
run against real PubMed/arXiv/Semantic Scholar plus a local LLM produced this
same field structure with genuine, verifiable citations — no fabricated
papers. The exact `confidence`/`caveats`/`tools_used` values above are
illustrative of the mechanism, not a literal transcript of one run.)*

## Entry point

Path A (LLM tool loop) — no custom handler class. Configuration lives in
`tool_schemas.py` / `tools.py` / `prompt.py` / `agent.card.json` / `config.py`
as described below. Run it with `python -m agent_skeleton.serve serve-a2a`.

## Dependencies

- Python packages: see `pyproject.toml` (`a2a-sdk[http-server]==0.3.2`,
  `openai>=1.40`, `uvicorn>=0.30`). No extra packages for the search tools —
  they use only the Python standard library (`urllib`, `xml.etree`).
- System binaries: none.
- Hardware: none (no local model; calls a hosted/remote LLM endpoint).
- Secrets (env vars, never committed): `OPENAI_API_KEY` (required, any
  placeholder for vLLM), `OPENAI_BASE_URL` (optional, for a self-hosted
  endpoint), `SEMANTIC_SCHOLAR_API_KEY` (optional, raises the rate limit).

---

# agent_skeleton (framework this agent is built on)

A small, copy-to-start template for building an **A2A agent**. It hands you the
~70% of every agent that is plumbing (the LLM loop, the A2A server wiring, request
parsing, the dual-channel response) so you only write the part that is *your* agent.

There are **two main ways** to build on it:

- **Path A — an LLM tool loop.** You supply a system prompt + a set of tools; a
  frozen engine runs the model-calls-tools loop. Best when the agent's value is
  reasoning: deciding which tool to call, chaining calls, synthesizing an answer.
- **Path B — a custom handler.** You already have working code; you wrap it by
  subclassing `AgentHandler` and implementing one method. Best when you just want
  existing code reachable as an agent.

> There's also an optional third path — front an existing HTTP/API endpoint with an
> LLM loop, writing no code — in the self-contained
> [`endpoint_wrapper/`](endpoint_wrapper/README.md) subpackage.

When your agent is ready, [`HACKATHON_CHEATSHEET.md`](HACKATHON_CHEATSHEET.md) covers
what to include (README, dependencies, secrets) and how to hand it over.

---

## Install

The import package is `agent_skeleton`; this folder is `agent-skeleton`. Install it
editable so the import name resolves:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

The Path-A **engine** and the `serve check` command run on the standard library
alone — you can validate an agent without installing anything. `a2a-sdk` + `uvicorn`
(pulled by `pip install -e .`) are only needed to actually **serve**.

---

## Path A — build an LLM tool loop

Edit four "write" files; leave everything else alone:

| File | You write |
|---|---|
| `tool_schemas.py` | `TOOL_SCHEMAS` — a JSON description of each tool (OpenAI Chat Completions shape) |
| `tools.py` | one Python function per tool + the `TOOL_REGISTRY` `{name: fn}` map |
| `prompt.py` | `SYSTEM_PROMPT` + `normalize_result()` (the stable output shape) |
| `agent.card.json` | your agent's name, url, and skills |

The rules that keep a tool correct (checked for you — see below):

- each function's keyword args are named **exactly** like its schema properties;
- every **optional** property (not in `required`) has a Python default;
- each function returns a JSON-able dict.

Then verify and run:

```bash
python -m agent_skeleton.serve check       # validates schemas <-> functions (no deps, no LLM)
python -m agent_skeleton.serve serve-a2a   # runs the agent over A2A (needs a2a-sdk + uvicorn)
```

`serve check` is the safety net: it fails fast if a schema and its function
disagree, in both directions, so you never discover a mismatch at runtime.

For an LLM: set `OPENAI_API_KEY` (any non-empty placeholder for a local vLLM) and
optionally `OPENAI_BASE_URL`. Against vLLM, launch it with `--enable-auto-tool-choice
--tool-call-parser <parser>`, or the model silently stops calling tools.

### Path A without editing the template in place

If you'd rather not edit the module globals, build an `AgentSpec` in your own script:

```python
from agent_skeleton import llm_wrapper_spec
spec = llm_wrapper_spec(
    name="My Agent",
    system_prompt="You are ...",
    preset_tools=["calculator", "current_time"],   # from system_tools/preset_tools
)
# from agent_skeleton.serve import create_app, load_agent_card
# app = create_app(load_agent_card("agent.card.json"), spec=spec)  # serve under uvicorn
```

---

## Path B — wrap your own code as a handler

You do **not** rewrite your code — you add a thin adapter class:

```python
from agent_skeleton import AgentHandler, FileInput

class MyHandler(AgentHandler):
    async def handle_structured(self, user_input, files=[], context=None) -> dict:
        # ... call your real code ...
        return {"answer": "the human-readable reply"}   # "answer" is REQUIRED
```

- `user_input` is the caller's text; `files` are attached files (`.bytes`,
  `.name`, `.as_tempfile()`); declare a `context` parameter to receive per-user
  credentials.
- If your code is blocking, wrap it in `await asyncio.to_thread(...)` so the
  heartbeat keeps flowing.

Run it locally:

```bash
python -m agent_skeleton.serve serve-handler --file handler.py --class MyHandler --port 9110
```

The framework gives you, for free: A2A request parsing, base64 file decoding into
`FileInput`, a heartbeat (so long calls don't time out), a runtime cap, credential
injection, error handling, and the dual machine+human response. See
[`INTEGRATION_GUIDE.md`](INTEGRATION_GUIDE.md) for the full walkthrough (the six
questions to answer about your code, dependencies, credentials, and a worked example).

---

## File map — where to edit, where not to

**Write (Path A):** `tool_schemas.py`, `tools.py`, `prompt.py`, `agent.card.json`, `config.py` (defaults).
**Write (Path B):** your `handler.py` (subclass `AgentHandler`).
**Copy — the frozen plumbing, rarely edited:**

| File | Role |
|---|---|
| `llm_loop.py` | the generic Chat-Completions tool loop (`run_tool_loop`, `run_agent`) |
| `spec.py` | `AgentSpec` — prompt + tools as data; one engine serves many agents |
| `executor.py` | `SkeletonAgentExecutor` — the Path-A A2A boundary |
| `handler_executor.py` | `HandlerExecutor` — wraps any `AgentHandler` for A2A (heartbeat, runtime cap, credentials) |
| `base.py` | `AgentHandler` + `FileInput` (the Path-B contract) |
| `a2a_runtime.py` | a2a-sdk import guard + `data_part`/`text_part`/`task_updater` |
| `serve.py` | `create_app` + `check` / `serve-a2a` / `serve-handler` |

---

## How it works (concepts)

- **Stateless tool loop.** Chat Completions has no server-side memory, so the loop
  holds the whole `messages` history locally and resends it each step, appending the
  assistant's tool-call message *before* the tool results. Tool calls are read from
  the model's typed `tool_calls` field — never regex-parsed.
- **Dual-channel response.** Every reply carries a machine-readable `DataPart`
  (structured output the planner reads) *and* a human-readable text message.
- **The alignment check** (`tools.validate_tool_registry`) reconciles each tool
  schema against its function signature; it runs in `create_app` and `serve check`.
  (A tool that declares `**kwargs` opts out of the check.)

---

## Testing

```bash
python -m agent_skeleton.serve check                                 # schema/function alignment (stdlib only)
python -m agent_skeleton.tests.test_wrapper                          # engine tests
python -m agent_skeleton.tests.test_preset_tools                     # preset-tool tests
python -m agent_skeleton.endpoint_wrapper.tests.test_call_endpoint    # optional endpoint feature
python -m agent_skeleton.endpoint_wrapper.tests.test_manager
python -m agent_skeleton.endpoint_wrapper.tests.test_operations
```

Because `a2a_runtime.py` degrades to a no-op when `a2a-sdk` is absent, you can import
the package, unit-test tool bodies, and run `serve check` without installing the SDK;
only serving requires it.

> **Note on `pytest`:** the commands the template previously documented here
> (`python -m pytest agent_skeleton/tests -q`) do not work — see
> [Repo feedback](#repo-feedback) below for the root cause. `pytest --collect-only`
> against any test file succeeds (it correctly finds all 40 tests), but actually
> *running* them under pytest fails every time, on every file, whether invoked
> as a directory or a single file. Every test file has a `python -m <module>`
> fallback entry point (used above) that runs the exact same test functions
> without going through pytest's collection at all, and all 40 pass this way —
> that's the one verified-working path today.

## Repo feedback

Filed while building this agent — see the issue for full repro steps and root
cause: **the documented `pytest` test commands are completely broken on a
fresh clone** (`ModuleNotFoundError` for the literal documented path, and
`ImportError: attempted relative import with no known parent package` for
every test once you fix the path). Root cause: pytest creates a `Package`
collector for any directory containing `__init__.py`; since this repo's
package lives at the repo root (`package-dir = {agent_skeleton = "."}`) and
the repo's on-disk directory is named `agent-skeleton` (hyphen, not a valid
Python identifier), pytest can't build a dotted module name for that `Package`
node's own import and fails importing it under the bogus name `__init__` with
no parent package — before it ever gets to your actual test file. This
reproduces on every invocation (not flaky), independent of OS, `--rootdir`, or
`--import-mode`. Full analysis and a recommended fix (a
`src/agent_skeleton/`-style layout so the repo root itself doesn't contain
`__init__.py`) filed upstream at:

**Issue:** _TODO — paste the URL here after filing on `washu-dev/agent-skeleton`_
