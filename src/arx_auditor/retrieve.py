from arx_auditor.state import AuditState

# ---------------------------------------------------------------------------
# Plain Python — testable without LangGraph
# ---------------------------------------------------------------------------

def rag_lookup(control_id: str) -> str:
    """Return the control text for a given control_id.

    Stub until M5 wires up ChromaDB + Cohere rerank. Returns an empty string
    so the graph runs end-to-end before the RAG layer exists.
    """
    return ""


# ---------------------------------------------------------------------------
# Thin node wrapper
# ---------------------------------------------------------------------------

def retrieve(state: AuditState) -> dict:
    """Node: fetch control text for every finding that has a control_id."""
    retrieved = {
        f["control_id"]: rag_lookup(f["control_id"])
        for f in state["findings"]
        if f["control_id"]
    }
    return {"retrieved": retrieved}
