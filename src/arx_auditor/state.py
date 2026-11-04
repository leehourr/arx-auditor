from typing import Annotated, Literal, NotRequired, TypedDict
import operator


class Finding(TypedDict):
    id: str                          # e.g. "F-014"
    source: Literal["burp", "nessus"]
    title: str
    evidence: str                    # host/port/URL + scanner detail
    framework: str                   # filled by router: "owasp" | "cis" | "cve"
    control_id: str                  # e.g. "CIS-2.1.1" — filled after routing


class AuditState(TypedDict):
    findings: list[Finding]                              # replace-on-write (default reducer)
    retrieved: dict[str, str]                            # control_id -> control text (RAG, M5)
    verdicts: Annotated[list[dict], operator.add]        # append — safe across M6 fan-out
    final_verdicts: list[dict]                           # M9: gate writes reviewed set here (replace)
    needs_review: Annotated[list[str], operator.add]     # finding ids awaiting human gate (M9)
    cost_usd: Annotated[float, operator.add]             # accumulated LLM call cost
    report_path: str
    client_id: NotRequired[str]                          # M8: store namespace key per client
