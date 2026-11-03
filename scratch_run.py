"""
Scratch runner — stream the graph in two modes to debug.
Switch between v1 (conditional edge) and v2 (Command) by changing the import.

    python scratch_run.py
"""
from arx_auditor.graph import build_graph_v1, build_graph_v2

init = {
    "findings": [],
    "retrieved": {},
    "verdicts": [],
    "needs_review": [],
    "cost_usd": 0.0,
    "report_path": "",
}

for label, app in [("v1 — conditional edge", build_graph_v1().compile()),
                   ("v2 — Command",           build_graph_v2().compile())]:
    print("=" * 60)
    print(f"  {label}")
    print("=" * 60)
    for chunk in app.stream(init, stream_mode="updates"):
        node, update = next(iter(chunk.items()))
        findings  = update.get("findings",     [])
        retrieved = update.get("retrieved",    None)
        needs_rev = update.get("needs_review", [])

        if findings:
            print(f"  [{node}] findings: {len(findings)}")
            for f in findings:
                print(f"    {f['id']}  fw={f['framework']:6s}  cid={f['control_id'] or '(none)':35s}  {f['title'][:45]}")
        elif retrieved is not None:
            print(f"  [{node}] retrieved: {len(retrieved)} control_ids")
        elif needs_rev:
            print(f"  [{node}] manual_triage: {needs_rev}")
        else:
            print(f"  [{node}]")
    print()
