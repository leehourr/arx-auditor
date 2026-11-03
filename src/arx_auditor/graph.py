from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from arx_auditor.classify import classify_one, fan_out_findings
from arx_auditor.parse import normalize, parse_scans
from arx_auditor.retrieve import retrieve
from arx_auditor.state import AuditState

# ---------------------------------------------------------------------------
# M6 — Send fan-out topology
#
# Shape:
#   parse_scans → normalize → retrieve
#                                └─(fan_out_findings)──▶ classify_one ──▶ END
#                                  [one Send per finding; N copies run in parallel]
#
# fan_out_findings is a routing function (returns list[Send]), not a node.
# classify_one receives a payload dict, not the full AuditState.
# All classify_one copies append into verdicts via the operator.add reducer (M2).
# ---------------------------------------------------------------------------


def build_graph() -> StateGraph:
    g = StateGraph(AuditState)

    g.add_node("parse_scans", parse_scans)
    g.add_node("normalize", normalize)
    g.add_node("retrieve", retrieve)
    g.add_node("classify_one", classify_one)

    g.add_edge(START, "parse_scans")
    g.add_edge("parse_scans", "normalize")
    g.add_edge("normalize", "retrieve")
    g.add_conditional_edges("retrieve", fan_out_findings, ["classify_one"])
    g.add_edge("classify_one", END)

    return g


# ---------------------------------------------------------------------------
# M7 — compile with checkpointer
#
# InMemorySaver: snapshots in RAM — good for dev/tests, gone on restart.
# SqliteSaver:   snapshots on disk — survive crashes and overnight human pauses.
#
# Usage:
#   from langgraph.checkpoint.sqlite import SqliteSaver
#   app = make_app(SqliteSaver.from_conn_string("checkpoints.db"))
# ---------------------------------------------------------------------------


def make_app(checkpointer=None):
    """Compile the graph with an optional checkpointer.

    No checkpointer → stateless (no resume, no history).
    Pass InMemorySaver() for dev or SqliteSaver for prod.
    """
    return build_graph().compile(checkpointer=checkpointer)


# Default export: InMemorySaver so thread_id / state history work out of the box.
app = make_app(checkpointer=InMemorySaver())
