from arx_auditor.route import assign_control_id, decide_framework
from arx_auditor.state import AuditState

# ---------------------------------------------------------------------------
# Plain Python — testable without LangGraph
# ---------------------------------------------------------------------------

def rag_lookup(control_id: str) -> str:
    """Return the control text for a given control_id.

    Stub until ChromaDB + Cohere rerank is wired. Returns empty string so the
    graph runs end-to-end before the RAG layer exists.
    """
    return ""


# ---------------------------------------------------------------------------
# Thin node wrapper
# ---------------------------------------------------------------------------

def retrieve(state: AuditState) -> dict:
    """Node: stamp control_ids onto findings (if missing), then fetch control text.

    Folded here because knowing what to retrieve and assigning the id are the
    same concern. M5's router node is gone in M6; this replaces its id-assignment
    role without taking on routing responsibility.
    """
    findings = []
    retrieved = {}

    for f in state["findings"]:
        if not f["control_id"]:
            fw = decide_framework(f)
            cid = assign_control_id(f, fw)
            f = {**f, "control_id": cid}
        findings.append(f)
        if f["control_id"]:
            retrieved[f["control_id"]] = rag_lookup(f["control_id"])

    return {"findings": findings, "retrieved": retrieved}
