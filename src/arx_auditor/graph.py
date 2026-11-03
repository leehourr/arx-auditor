from langgraph.graph import END, START, StateGraph

from arx_auditor.parse import normalize, parse_scans
from arx_auditor.retrieve import retrieve
from arx_auditor.state import AuditState


def build_graph() -> StateGraph:
    g = StateGraph(AuditState)

    g.add_node("parse_scans", parse_scans)
    g.add_node("normalize", normalize)
    g.add_node("retrieve", retrieve)

    g.add_edge(START, "parse_scans")
    g.add_edge("parse_scans", "normalize")
    g.add_edge("normalize", "retrieve")
    g.add_edge("retrieve", END)

    return g


app = build_graph().compile()
