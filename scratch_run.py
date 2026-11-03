"""
Scratch runner — stream the graph in two modes to debug.
Not part of the package. Delete or keep for dev reference.

    python scratch_run.py
"""
from arx_auditor.graph import app

init = {
    "findings": [],
    "retrieved": {},
    "verdicts": [],
    "needs_review": [],
    "cost_usd": 0.0,
    "report_path": "",
}

print("=" * 60)
print("stream_mode='updates'  — delta each node returned")
print("=" * 60)
for chunk in app.stream(init, stream_mode="updates"):
    node, update = next(iter(chunk.items()))
    findings = update.get("findings", [])
    retrieved = update.get("retrieved", {})
    if findings:
        print(f"  [{node}] findings: {len(findings)}")
        for f in findings:
            print(f"    {f['id']}  {f['source']:6s}  {f['title'][:60]}")
    elif retrieved is not None and "retrieved" in update:
        print(f"  [{node}] retrieved control text for {len(retrieved)} control_ids")
    else:
        print(f"  [{node}] {update}")

print()
print("=" * 60)
print("stream_mode='values'   — full state snapshot after each node")
print("=" * 60)
for chunk in app.stream(init, stream_mode="values"):
    print(
        f"  findings={len(chunk['findings']):3d}  "
        f"retrieved={len(chunk['retrieved']):3d}  "
        f"verdicts={len(chunk['verdicts']):3d}"
    )
