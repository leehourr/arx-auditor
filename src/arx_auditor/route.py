from typing import Literal

from langgraph.constants import END
from langgraph.types import Command

from arx_auditor.state import AuditState, Finding

Framework = Literal["owasp", "cis", "cve", "unknown"]

# ---------------------------------------------------------------------------
# Plain Python — testable without LangGraph
# ---------------------------------------------------------------------------

def decide_framework(f: Finding) -> Framework:
    """Map a finding to its audit framework.

    Burp findings always map to OWASP (web-app scope).
    Nessus findings carry framework set at parse time ("cis" or "cve").
    Anything else gets flagged as unknown for manual triage.
    """
    fw = f.get("framework", "")
    if fw in ("owasp", "cis", "cve"):
        return fw  # type: ignore[return-value]
    # fallback: infer from source
    if f["source"] == "burp":
        return "owasp"
    if f["source"] == "nessus":
        return "cve"
    return "unknown"


def assign_control_id(f: Finding, framework: Framework) -> str:
    """Return a placeholder control_id.

    Stub — M5 RAG (ChromaDB + Cohere) replaces this with a real lookup.
    Format mirrors what the retrieve node expects: 'FRAMEWORK-<slug>'.
    """
    slug = f["title"][:30].lower().replace(" ", "-").replace("/", "-")
    if framework == "unknown":
        return ""
    return f"{framework.upper()}-{slug}"


# ---------------------------------------------------------------------------
# Option 1 — conditional edge + pure routing function
#
# Wired as:
#   g.add_conditional_edges(
#       "retrieve",
#       route_by_framework,
#       {"owasp": "classify_owasp", "cis": "classify_cis",
#        "cve": "classify_cve", "unknown": "manual_triage"},
#   )
#
# Rule: routing functions MUST be pure — read state, return a string.
# No state mutation, no model calls. If you need both, use Option 2.
# ---------------------------------------------------------------------------

def route_by_framework(state: AuditState) -> str:
    """Pure routing function: reads the first unrouted finding, returns its
    destination node name. Does not touch state."""
    for f in state["findings"]:
        if not f["control_id"]:
            return decide_framework(f)
    return "unknown"


# ---------------------------------------------------------------------------
# Option 2 — node returns Command (decide + update state in one step)
#
# Wired as a normal node:
#   g.add_node("router", router)
#   g.add_edge("retrieve", "router")
#
# Use when the node that figures out the framework should also stamp it onto
# the finding. Command(update=..., goto=...) is atomic: the state write and
# the routing decision land together.
# ---------------------------------------------------------------------------

def router(state: AuditState) -> Command[Literal[
    "classify_owasp", "classify_cis", "classify_cve", "manual_triage"
]]:
    """Node: stamp framework + control_id onto the first unrouted finding,
    then jump to the matching classify node."""
    findings = list(state["findings"])

    for i, f in enumerate(findings):
        if f["control_id"]:
            continue  # already routed

        fw = decide_framework(f)
        cid = assign_control_id(f, fw)
        findings[i] = {**f, "framework": fw, "control_id": cid}

        dest = "manual_triage" if fw == "unknown" else f"classify_{fw}"
        return Command(
            update={"findings": findings},
            goto=dest,
        )

    # all findings routed — nothing left to classify
    return Command(goto=END)
