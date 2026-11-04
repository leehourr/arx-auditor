from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.store.base import BaseStore
from langgraph.types import Send
from pydantic import BaseModel

from arx_auditor.state import AuditState

_MODEL = "claude-opus-4-8"

_SYSTEM = (
    "You are a senior security auditor. Classify a scanner finding into exactly one bucket.\n\n"
    "Buckets:\n"
    "  Fix           — real vulnerability, must remediate.\n"
    "  Suppress      — false positive or not applicable in this environment.\n"
    "  Exception     — real risk, client formally accepts it (business decision).\n"
    "  Already-fixed — remediated since the scan was taken.\n\n"
    "Return the bucket name and a single sentence justifying the call."
)


class _VerdictOut(BaseModel):
    bucket: Literal["Fix", "Suppress", "Exception", "Already-fixed"]
    reason: str


_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = ChatAnthropic(model=_MODEL, max_tokens=512).with_structured_output(
            _VerdictOut
        )
    return _llm


# ---------------------------------------------------------------------------
# Plain Python — testable without LangGraph
# ---------------------------------------------------------------------------


def llm_classify(finding: dict, control: str) -> dict:
    """Call the LLM with pinned context: one finding + its control text."""
    framework = finding["framework"].upper()
    control_block = (
        f"Control reference ({framework}):\n{control}"
        if control
        else f"No control text retrieved — apply general {framework} knowledge."
    )

    result: _VerdictOut = _get_llm().invoke(
        [
            SystemMessage(content=_SYSTEM),
            HumanMessage(
                content=(
                    f"Finding: {finding['title']}\n"
                    f"Evidence: {finding['evidence']}\n"
                    f"Framework: {framework}\n\n"
                    f"{control_block}"
                )
            ),
        ]
    )
    return {
        "id": finding["id"],
        "title": finding["title"],
        "framework": finding["framework"],
        "bucket": result.bucket,
        "reason": result.reason,
    }


# ---------------------------------------------------------------------------
# LangGraph nodes — used via Send fan-out in graph.py
# ---------------------------------------------------------------------------


def fan_out_findings(state: AuditState) -> list[Send]:
    """Routing function: one Send per finding → N parallel classify_one copies."""
    client_id = state.get("client_id", "default")
    return [
        Send(
            "classify_one",
            {
                "finding": f,
                "control": state["retrieved"].get(f["control_id"], ""),
                "client_id": client_id,
            },
        )
        for f in state["findings"]
    ]


# M8 — store namespace: ("client_exceptions", client_id)
# Key: finding.control_id  (same control accepted once → skip re-review forever)
# Written by M9 gate after human approval; read here to short-circuit the LLM.

def classify_one(payload: dict, store: BaseStore) -> dict:
    """Node (launched by Send): checks cross-run store before calling the LLM.

    If the client previously accepted an Exception for this control_id,
    the stored verdict is returned directly — no LLM call, no re-review.
    """
    finding = payload["finding"]
    control = payload["control"]
    client_id = payload["client_id"]
    control_id = finding["control_id"]

    if control_id:
        namespace = ("client_exceptions", client_id)
        cached = store.get(namespace, control_id)
        if cached is not None:
            v = dict(cached.value)
            v["cached"] = True
            return {"verdicts": [v]}

    v = llm_classify(finding, control)
    return {"verdicts": [v]}
