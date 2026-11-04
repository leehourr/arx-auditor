from langgraph.store.base import BaseStore
from langgraph.types import interrupt

from arx_auditor.state import AuditState

_REVIEW_BUCKETS = {"Suppress", "Exception"}


def _control_id_for(findings: list, finding_id: str) -> str:
    for f in findings:
        if f["id"] == finding_id:
            return f.get("control_id", "")
    return ""


# ---------------------------------------------------------------------------
# M9 — HITL gate
#
# Runs once after all classify_one fan-out branches converge.
# Pauses on Suppress / Exception only — Fix and Already-fixed pass through.
#
# interrupt() serializes graph state to the SQLite checkpointer and halts.
# Execution resumes when the caller passes Command(resume={...}).
#
# Resume payload expected:
#   {
#     "approved": ["F-001", "F-003"],   # keep bucket as-is
#     "rejected": ["F-002"],            # flip back to Fix
#   }
#
# M8 write-back: approved Exceptions are stored in the cross-run store so
# future runs skip re-review for the same control_id.
# ---------------------------------------------------------------------------


def gate(state: AuditState, store: BaseStore) -> dict:
    pending = [v for v in state["verdicts"] if v["bucket"] in _REVIEW_BUCKETS]

    if not pending:
        return {"final_verdicts": state["verdicts"]}

    decisions = interrupt({
        "message": "Human review required — approve or reject each finding.",
        "pending": [
            {"id": v["id"], "title": v["title"], "bucket": v["bucket"], "reason": v["reason"]}
            for v in pending
        ],
    })

    approved_ids = set(decisions.get("approved", []))
    rejected_ids = set(decisions.get("rejected", []))
    amendments = decisions.get("amendments", {})   # {finding_id: new_reason_str}
    client_id = state.get("client_id", "default")

    final = []
    for v in state["verdicts"]:
        v_out = {**v}
        if v["id"] in amendments:
            v_out["reason"] = amendments[v["id"]]
        if v["id"] in rejected_ids:
            final.append({**v_out, "bucket": "Fix", "reason": f"[gate rejected] {v_out['reason']}"})
        else:
            final.append(v_out)
            if v["id"] in approved_ids and v["bucket"] == "Exception":
                control_id = _control_id_for(state["findings"], v["id"])
                if control_id:
                    store.put(
                        ("client_exceptions", client_id),
                        control_id,
                        v_out,
                    )

    return {"final_verdicts": final}
