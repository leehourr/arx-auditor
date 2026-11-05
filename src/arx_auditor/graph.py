import sqlite3

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore
from langgraph.store.sqlite import SqliteStore
from langgraph.types import RetryPolicy

from arx_auditor.classify import classify_one, fan_out_findings
from arx_auditor.gate import gate
from arx_auditor.parse import normalize, parse_scans
from arx_auditor.retrieve import retrieve
from arx_auditor.state import AuditState

# ---------------------------------------------------------------------------
# M6 + M9 + M11 — Send fan-out → HITL gate topology + production guardrails
#
# Shape:
#   parse_scans → normalize → retrieve
#                                └─(fan_out_findings)──▶ classify_one ──┐
#                                  [one Send per finding]                │
#                                                                        ▼
#                                                                      gate ──▶ END
#                                                                  [interrupt() on
#                                                                   Suppress/Exception]
#
# All classify_one copies converge before gate runs (scatter-gather).
# gate reads verdicts (append-reduced), writes final_verdicts (replace).
#
# M11 guardrails:
#   RetryPolicy(max_attempts=3) on classify_one — survives transient API 503s.
#   recursion_limit passed at invoke/stream time — sized to findings count so
#   an accidental loop trips the alarm rather than running forever.
# ---------------------------------------------------------------------------

# Sized for worst-case: 200 findings × ~3 internal steps + slack.
# Hit this limit → bug in routing, not a normal run.
_RECURSION_LIMIT = 700


def build_graph() -> StateGraph:
    g = StateGraph(AuditState)

    g.add_node("parse_scans", parse_scans)
    g.add_node("normalize", normalize)
    g.add_node("retrieve", retrieve)
    g.add_node(
        "classify_one",
        classify_one,
        retry_policy=RetryPolicy(max_attempts=3),
    )
    g.add_node("gate", gate)

    g.add_edge(START, "parse_scans")
    g.add_edge("parse_scans", "normalize")
    g.add_edge("normalize", "retrieve")
    g.add_conditional_edges("retrieve", fan_out_findings, ["classify_one"])
    g.add_edge("classify_one", "gate")
    g.add_edge("gate", END)

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


def make_app(checkpointer=None, store=None):
    """Compile the graph.

    checkpointer — SqliteSaver for pause/resume durability (SqliteSaver or InMemorySaver).
    store        — SqliteStore for cross-run Exception cache (SqliteStore or InMemoryStore).

    Always pass recursion_limit=_RECURSION_LIMIT in the config at invoke/stream time:
        config = {"recursion_limit": _RECURSION_LIMIT, "configurable": {"thread_id": "..."}}
    """
    return build_graph().compile(checkpointer=checkpointer, store=store)


# Default module-level export uses in-memory backends (import-safe, no file side effects).
app = make_app(checkpointer=InMemorySaver(), store=InMemoryStore())
