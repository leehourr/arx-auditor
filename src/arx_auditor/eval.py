import json
from pathlib import Path

from arx_auditor.classify import classify_one
from arx_auditor.state import AuditState


def load_golden(path: str | Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_eval(golden: list[dict]) -> float:
    """Replay classify_one against each golden row, return agreement rate.

    Each row: {finding, control, human_bucket}
    Agreement = tool bucket matches human bucket (exact string match).
    """
    agree = 0
    for row in golden:
        state: AuditState = {
            "findings": [row["finding"]],
            "retrieved": {row["finding"]["control_id"]: row["control"]},
            "verdicts": [],
            "final_verdicts": [],
            "needs_review": [],
            "cost_usd": 0.0,
            "report_path": "",
        }
        result = classify_one(state)
        verdicts = result.get("verdicts", [])
        if verdicts and verdicts[0].get("bucket") == row["human_bucket"]:
            agree += 1
    return agree / len(golden)
