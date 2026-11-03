from langgraph.graph import END, START, StateGraph

from arx_auditor.parse import normalize, parse_scans
from arx_auditor.retrieve import retrieve
from arx_auditor.route import route_by_framework, router
from arx_auditor.state import AuditState

# ---------------------------------------------------------------------------
# Stub classify nodes — replaced by real LLM calls in M6
# ---------------------------------------------------------------------------

def classify_owasp(state: AuditState) -> dict:
    return {}


def classify_cis(state: AuditState) -> dict:
    return {}


def classify_cve(state: AuditState) -> dict:
    return {}


def manual_triage(state: AuditState) -> dict:
    """Finding matched no framework — flag for human review (feeds M9 gate)."""
    unrouted = [f["id"] for f in state["findings"] if not f["control_id"]]
    return {"needs_review": unrouted}


# ---------------------------------------------------------------------------
# Option 1 — conditional edge + pure routing function
#
# Shape:  parse_scans → normalize → retrieve
#                                       └─(route_by_framework)─▶ classify_owasp
#                                                              ├─▶ classify_cis
#                                                              ├─▶ classify_cve
#                                                              └─▶ manual_triage
# ---------------------------------------------------------------------------

def build_graph_v1() -> StateGraph:
    g = StateGraph(AuditState)

    g.add_node("parse_scans", parse_scans)
    g.add_node("normalize", normalize)
    g.add_node("retrieve", retrieve)
    g.add_node("classify_owasp", classify_owasp)
    g.add_node("classify_cis", classify_cis)
    g.add_node("classify_cve", classify_cve)
    g.add_node("manual_triage", manual_triage)

    g.add_edge(START, "parse_scans")
    g.add_edge("parse_scans", "normalize")
    g.add_edge("normalize", "retrieve")

    g.add_conditional_edges(
        "retrieve",
        route_by_framework,
        {
            "owasp":   "classify_owasp",
            "cis":     "classify_cis",
            "cve":     "classify_cve",
            "unknown": "manual_triage",
        },
    )

    g.add_edge("classify_owasp", END)
    g.add_edge("classify_cis", END)
    g.add_edge("classify_cve", END)
    g.add_edge("manual_triage", END)

    return g


# ---------------------------------------------------------------------------
# Option 2 — router node returns Command (update state + route atomically)
#
# Shape:  parse_scans → normalize → retrieve → router
#                                                 └─(Command.goto)─▶ classify_owasp
#                                                                  ├─▶ classify_cis
#                                                                  ├─▶ classify_cve
#                                                                  └─▶ manual_triage
# ---------------------------------------------------------------------------

def build_graph_v2() -> StateGraph:
    g = StateGraph(AuditState)

    g.add_node("parse_scans", parse_scans)
    g.add_node("normalize", normalize)
    g.add_node("retrieve", retrieve)
    g.add_node("router", router)
    g.add_node("classify_owasp", classify_owasp)
    g.add_node("classify_cis", classify_cis)
    g.add_node("classify_cve", classify_cve)
    g.add_node("manual_triage", manual_triage)

    g.add_edge(START, "parse_scans")
    g.add_edge("parse_scans", "normalize")
    g.add_edge("normalize", "retrieve")
    g.add_edge("retrieve", "router")

    g.add_edge("classify_owasp", END)
    g.add_edge("classify_cis", END)
    g.add_edge("classify_cve", END)
    g.add_edge("manual_triage", END)

    return g


app = build_graph_v2().compile()
