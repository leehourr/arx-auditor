"""
Scratch runner — M6 fan-out stream + M7 state history.

Requires ANTHROPIC_API_KEY in the environment (real LLM calls from M6).

    python scratch_run.py
"""
from arx_auditor.graph import make_app
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()
app = make_app(checkpointer=checkpointer)

# M7: every run is identified by a thread_id — all its checkpoints share this key
config = {"configurable": {"thread_id": "debug-run-001"}}

init = {
    "findings": [],
    "retrieved": {},
    "verdicts": [],
    "needs_review": [],
    "cost_usd": 0.0,
    "report_path": "",
}

# ---------------------------------------------------------------------------
# M6 — stream updates as nodes run
# ---------------------------------------------------------------------------
print("=" * 60)
print("  M6 fan-out — updates stream")
print("=" * 60)

for chunk in app.stream(init, config=config, stream_mode="updates"):
    node, update = next(iter(chunk.items()))
    findings  = update.get("findings",  [])
    retrieved = update.get("retrieved", None)
    verdicts  = update.get("verdicts",  [])

    if findings:
        print(f"  [{node}] findings: {len(findings)}")
        for f in findings:
            print(f"    {f['id']}  fw={f['framework']:6s}  cid={f['control_id'][:35] or '(none)':35s}  {f['title'][:40]}")
    elif retrieved is not None:
        print(f"  [{node}] retrieved: {len(retrieved)} control_ids")
    elif verdicts:
        for v in verdicts:
            print(f"  [{node}] {v['id']:6s}  [{v['bucket']:14s}]  {v['reason'][:60]}")
    else:
        print(f"  [{node}]")

print()

# ---------------------------------------------------------------------------
# M7 — inspect every checkpoint the run created
# ---------------------------------------------------------------------------
print("=" * 60)
print("  M7 — state history (newest first)")
print("=" * 60)

for snap in app.get_state_history(config):
    next_nodes = snap.next or ("END",)
    n_findings = len(snap.values.get("findings", []))
    n_verdicts = len(snap.values.get("verdicts", []))
    print(
        f"  next={str(next_nodes[0]):22s}  "
        f"findings={n_findings:2d}  verdicts={n_verdicts:2d}  "
        f"ts={snap.created_at}"
    )

print()

# ---------------------------------------------------------------------------
# M7 — time travel: rewind to right before classify, re-run from there
# ---------------------------------------------------------------------------
print("=" * 60)
print("  M7 — time travel demo (re-run classify from earlier checkpoint)")
print("=" * 60)

history = list(app.get_state_history(config))
# find the checkpoint where retrieve just finished (next node = classify_one)
pre_classify = next(
    (s for s in history if s.next and s.next[0] == "classify_one"), None
)

if pre_classify:
    print(f"  rewinding to: next={pre_classify.next[0]}  verdicts before={len(pre_classify.values.get('verdicts', []))}")
    for chunk in app.stream(None, config=pre_classify.config, stream_mode="updates"):
        node, update = next(iter(chunk.items()))
        verdicts = update.get("verdicts", [])
        if verdicts:
            for v in verdicts:
                print(f"  [{node}] {v['id']:6s}  [{v['bucket']:14s}]  {v['reason'][:60]}")
        else:
            print(f"  [{node}]")
else:
    print("  (no pre-classify checkpoint found — run the graph first)")
