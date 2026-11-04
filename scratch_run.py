# %% [markdown]
# # scratch_run — M6 / M7 / M8 interactive harness
#
# Run each `# %%` cell independently in VS Code (Python Interactive).
# Requires `ANTHROPIC_API_KEY` in the environment — real LLM calls happen in M6.
#
# Cell order matters: setup → M6 → M7 → M8.
# Re-run any cell in isolation without re-firing the whole script.

# %% setup
import os
import sqlite3

from dotenv import load_dotenv

load_dotenv()

from arx_auditor.graph import make_app
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import SqliteStore

DB_PATH = os.getenv("DB_PATH", "dev.db")
CLIENT_ID = os.getenv("CLIENT_ID", "acme-q4-2026")

conn_cp = sqlite3.connect(DB_PATH, check_same_thread=False)
conn_store = sqlite3.connect(DB_PATH, check_same_thread=False)

checkpointer = SqliteSaver(conn_cp)
store = SqliteStore(conn_store)
app = make_app(checkpointer=checkpointer, store=store)

# M7: every run is identified by a thread_id — all its checkpoints share this key
config = {"configurable": {"thread_id": "debug-run-001"}}

init = {
    "findings": [],
    "retrieved": {},
    "verdicts": [],
    "needs_review": [],
    "cost_usd": 0.0,
    "report_path": "",
    "client_id": CLIENT_ID,
}

# %% M6 — fan-out stream
# Fires real LLM calls. Each classify_one runs in parallel via Send.
# Watch for [CACHED] on any finding whose control_id is already in the store.
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
            cached = " [CACHED]" if v.get("cached") else ""
            print(f"  [{node}] {v['id']:6s}  [{v['bucket']:14s}]{cached}  {v['reason'][:60]}")
    else:
        print(f"  [{node}]")

print()

# %% M7 — state history
# Shows every checkpoint the M6 run created, newest first.
# Requires the M6 cell to have run first (uses same config / thread_id).
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

# %% M7 — time travel
# Rewinds to the checkpoint just before classify and re-runs from there.
# Demonstrates that you can replay any branch of the graph from a saved snapshot.
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
                cached = " [CACHED]" if v.get("cached") else ""
                print(f"  [{node}] {v['id']:6s}  [{v['bucket']:14s}]{cached}  {v['reason'][:60]}")
        else:
            print(f"  [{node}]")
else:
    print("  (no pre-classify checkpoint found — run the graph first)")

print()

# %% M8 — cross-run store
# Seeds one Exception into the store (simulating M9 gate approval),
# then re-runs the graph on a new thread. The seeded finding should print
# [CACHED — no LLM call] instead of firing a new classify call.
print("=" * 60)
print("  M8 — cross-run store: pre-seed one Exception, re-run new thread")
print("=" * 60)

# Peek at what control_ids came out of run 1 so we can seed one
first_run_verdicts = app.get_state(config).values.get("verdicts", [])
if not first_run_verdicts:
    print("  (no verdicts from run 1 — skipping M8 demo)")
else:
    # Pick the first verdict with a non-empty id as our seeded Exception
    seed_verdict = first_run_verdicts[0]
    seed_control = None
    # find the control_id for this finding id
    first_run_findings = app.get_state(config).values.get("findings", [])
    for f in first_run_findings:
        if f["id"] == seed_verdict["id"] and f["control_id"]:
            seed_control = f["control_id"]
            break

    if seed_control:
        namespace = ("client_exceptions", CLIENT_ID)
        store.put(
            namespace,
            seed_control,
            {
                "id": seed_verdict["id"],
                "title": seed_verdict["title"],
                "framework": seed_verdict["framework"],
                "bucket": "Exception",
                "reason": "[pre-seeded] Client formally accepted this risk in Q3 review.",
            },
        )
        print(f"  seeded Exception for control_id={seed_control}")

        # Run graph on a new thread — the seeded finding should skip the LLM
        config2 = {"configurable": {"thread_id": "debug-run-002"}}
        init2 = {**init}
        for chunk in app.stream(init2, config=config2, stream_mode="updates"):
            node, update = next(iter(chunk.items()))
            verdicts = update.get("verdicts", [])
            if verdicts:
                for v in verdicts:
                    cached = " [CACHED — no LLM call]" if v.get("cached") else ""
                    print(f"  [{node}] {v['id']:6s}  [{v['bucket']:14s}]{cached}  {v['reason'][:60]}")
    else:
        print("  (no control_id on first verdict — skipping store seed)")

# %% M9 — HITL gate: run until interrupt, then resume
# The graph pauses at gate when any Suppress/Exception is found.
# interrupt() state is checkpointed to SQLite — safe to close and reopen.
# Resume by passing Command(resume={...}) with approved/rejected ids.
from langgraph.types import Command

print("=" * 60)
print("  M9 — HITL gate demo")
print("=" * 60)

config3 = {"configurable": {"thread_id": "debug-run-003"}}
init3 = {**init}

interrupted_at = None
for chunk in app.stream(init3, config=config3, stream_mode="updates"):
    node, update = next(iter(chunk.items()))
    verdicts = update.get("verdicts", [])
    final = update.get("final_verdicts", [])

    if verdicts:
        for v in verdicts:
            cached = " [CACHED]" if v.get("cached") else ""
            print(f"  [{node}] {v['id']:6s}  [{v['bucket']:14s}]{cached}  {v['reason'][:50]}")
    elif final:
        for v in final:
            print(f"  [{node}] {v['id']:6s}  [{v['bucket']:14s}]  FINAL  {v['reason'][:50]}")
    elif "__interrupt__" in update:
        interrupted_at = update["__interrupt__"]
        print(f"\n  *** INTERRUPTED — {len(interrupted_at[0].value['pending'])} finding(s) need review ***")
        for item in interrupted_at[0].value["pending"]:
            print(f"    {item['id']:6s}  [{item['bucket']:14s}]  {item['reason'][:55]}")
        break
    else:
        print(f"  [{node}]")

if interrupted_at:
    print()
    # Simulate senior auditor decision:
    #   - approve all pending
    #   - amend the reason on the first one (e.g. add compensating control note)
    pending_ids = [item["id"] for item in interrupted_at[0].value["pending"]]
    first_id = pending_ids[0]
    print(f"  > approving all: {pending_ids}")
    print(f"  > amending reason on {first_id}")

    for chunk in app.stream(
        Command(resume={
            "approved": pending_ids,
            "rejected": [],
            "amendments": {
                first_id: "Accepted — compensating control documented in CAB-2026-11.",
            },
        }),
        config=config3,
        stream_mode="updates",
    ):
        node, update = next(iter(chunk.items()))
        final = update.get("final_verdicts", [])
        if final:
            print(f"\n  [{node}] final verdicts after gate:")
            for v in final:
                print(f"    {v['id']:6s}  [{v['bucket']:14s}]  {v['reason'][:55]}")
        else:
            print(f"  [{node}]")
