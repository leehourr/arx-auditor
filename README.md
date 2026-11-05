# arx-auditor

Turning a few hundred raw scan findings into a reviewed, cited, sign-off-ready audit report — the same way every single time. Point it at a scan dump (Nessus for cloud config and CVEs, Burp for web apps and APIs), it pulls the matching reference for each finding — a CIS benchmark control, an OWASP category, or the CVE/NVD record — drafts a disposition, parks everything at a human gate until someone signs off, then assembles the report. Built in LangGraph.

The teeth are under "general vs specific." A general agent is general because it decides — every run it re-chooses what to do, in what order, whether to stop. That flexibility is the entire point of a general agent, and it is exactly what you do not want in an audit, where the answer to "why'd you do it that way" has to be the same every time. arx-auditor is specific because the decisions are already made: the control flow, the gate, the retrieve-then-classify order are baked into the graph, not re-decided per run. You trade flexibility for a guarantee.

---

## Quick start

Built on LangGraph — the graph, the human gate, and the checkpointer that survives a restart all come from there. Two external API keys required: Anthropic for classification, Cohere for reranking.

`src`-layout package, not on PyPI — install editable from a clone:

```bash
uv sync --extra dev        # uv.lock is committed
# or: pip install -e ".[dev]"
```

Copy the env template and fill in both keys:

```bash
cp .env.example .env
# ANTHROPIC_API_KEY, COHERE_API_KEY, plus DB_PATH / CHROMA_PATH / CLIENT_ID
```

Drop the exact benchmark version you're assessing against into `controls/` (one pinned PDF per framework — that pinned version is what every finding retrieves against) and your scan exports alongside the samples in `data/samples/`.

There's no `arx-auditor` command yet. Two ways to run the graph:

```bash
langgraph dev     # LangGraph Studio: step through nodes, inspect state in the browser
```

Or step through `scratch_run.py` — a VS Code "Python Interactive" harness (`# %%` cells) that builds the app, streams the classify fan-out, and runs the human gate: it executes until the gate's `interrupt()`, you review the pending dispositions, then resume with `Command(resume={"approved": [...], "rejected": [...], "amendments": {...}})`. Programmatic entry is `make_app(checkpointer=..., store=...)` from `arx_auditor.graph`.

---

## What it's for

Start with the division of labor. Burp and Nessus scan the target and dump raw evidence — "port 443 serves TLS 1.0," "this S3 bucket is public" — a long, unranked list. The benchmark — a CIS control, an OWASP category, the CVE/NVD record — is the authoritative rule that evidence gets judged against. A scanner doesn't know which benchmark version you scoped, what the client contract covers, or that an internal port is firewalled off; that context lives in the pipeline. arx-auditor is the bridge: raw finding in, pinned control text pulled, judged disposition out.

A security engagement — cloud config, web app, API — produces a few hundred findings. Each one needs the same treatment: pull the relevant reference — a CIS control, an OWASP category, or the CVE/NVD record — decide what it is (fix it / suppress it / log an exception / already fixed), attach the evidence, and write it up so a reviewer can check the reasoning months later.

Done by hand, this is slow and drifts — finding #300 gets less care than finding #3. Done by pointing a general agent at the dump, it is fast but not reproducible: ask it twice and you get two different sets of decisions, and you cannot explain why it did what it did.

An audit deliverable has to be defensible. "Why was this finding suppressed?" must have the same answer today and at next year's review. That is the actual requirement, and it is a requirement about the *process*, not about how smart any single answer is.

---

## How the harness works

```
scan dump          CIS · OWASP · CVE/NVD
(Nessus, Burp)     reference text
                   (pinned, pre-chunked, embedded)
     |                   |
     v                   v
  ingest  ---------> hybrid retrieve  (per finding)
                         |
                         v
                   classify_one       drafts a disposition:
                   (fan-out)          Fix / Suppress / Exception / Already-fixed
                         |            + the control it cites + the evidence
                         v
                    human gate         execution blocks here until a
                   (durable HITL)      person signs off — nothing ships
                         |             on the model's say-so
                         v
                  report assembly
```

Every finding goes through the same three steps — retrieve, classify, gate — in the same order. The gate is a real stop, not a prompt asking the model to wait. Work parked at the gate survives a restart and resumes where it left off.

---

## Why the reference text is stored, not fetched live

The control text each finding retrieves against is a frozen, version-pinned copy — a handful of PDFs dropped into `controls/` at engagement setup, ingested once. That pin is the defensibility. "Why was this suppressed against CIS AWS Foundations v5.0.0, control 2.1.1?" has the same answer at next year's review because the text the model reasoned over hasn't moved, and you can show the exact chunk it cited.

Live web search breaks that. CIS ships a revision, the page edits or 404s, and the rerun disposes the finding differently with nothing to explain why. You'd also cite whatever is current instead of the version you scoped against. Picking the version is a human scoping decision made once, before classification — not something the pipeline guesses per finding.

CVEs are the same argument from a different angle. A CVE finding already carries its CVE id from the Nessus scan, so there's nothing to look up to identify it — but the NVD record behind that id does move: CVSS gets rescored, a CVE gets disputed or rejected. Pin the snapshot you assessed against for the same reason you pin the benchmark version. (The repo doesn't wire a CVE corpus yet — `rag_lookup` is a stub for every framework — so this is the design the store is built toward, not a working claim.)

So the store isn't overhead to shed. A live-search tool is the same retrieval machinery over a worse, non-reproducible corpus — and "just let the agent fetch them" assumes the sources are fetchable, which they aren't uniformly. OWASP's Top 10 and ASVS are public downloads; NVD has an API; but CIS Benchmark PDFs aren't at a crawlable URL at all — they're free, but gated behind a CIS account and a download form, so a general browsing agent (even a capable commercial one) lands on the registration wall, not the PDF. Getting the control text in is a human step either way.

This is also why the work is a graph and not an agent. Pinning the corpus freezes the inputs; baking the control flow into the graph freezes the steps. Same goal — an answer that comes out the same way next year — attacked from both ends. The next section is the other half.

---

## Why a pipeline, not a general agent + a RAG tool

Most of the gap a general agent has here is closable, and worth conceding up front:

- **Retrieval** — wire the agent to a tool that looks up control text and checks evidence, and it cites as well as this does. Don't build a pipeline to get retrieval.
- **Memory** — persist run state in a file and "runs once and forgets" goes away too.

What doesn't close is control flow. A RAG tool is passive — the agent still chooses when to call it, how often, and whether the result is enough — and under context pressure at finding #300 it can batch, shortcut, or skip the gate, and you can't prove it didn't. The graph can't: every finding goes through retrieve → classify → gate, enforced and logged, regardless of what the model samples on any given pass.

A prompt is an instruction you hope it follows. A graph is the instruction enforced. (Temperature 0 doesn't change this — it pins the sampling, not whether the step runs.)

---

## When to skip it

Use a general agent with a RAG tool instead if the job is:

- one-off, or a handful of findings
- exploratory — you are still figuring out what you are looking at
- internal-only, where no one will ask you to defend a decision later

The pipeline earns its weight at three things together: **volume, defensibility, and a clean handoff to whoever signs off.** That reviewer is usually the dev who owns the system, not the auditor alone — the gate hands them each disposition with its cited control and evidence, so they check the reasoning instead of re-running the analysis. If none of those three apply, the pipeline is overhead.

---

## License

TBD.
