from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
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
    return [
        Send(
            "classify_one",
            {
                "finding": f,
                "control": state["retrieved"].get(f["control_id"], ""),
            },
        )
        for f in state["findings"]
    ]


def classify_one(payload: dict) -> dict:
    """Node (launched by Send): sees only one finding and its control text."""
    v = llm_classify(payload["finding"], payload["control"])
    return {"verdicts": [v]}
