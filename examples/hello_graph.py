"""
M1 throwaway — the smallest LangGraph that runs.
Not part of the arx_auditor package. Run once to prove the machine works:

    python examples/hello_graph.py
    # => {'count': 11, 'log': ['step_a ran', 'step_b ran']}

Every module after this swaps ToyState for AuditState and these two
toy functions for real nodes. The five numbered lines never change.
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class ToyState(TypedDict):
    count: int
    log: list[str]


def step_a(state: ToyState) -> dict:
    return {"count": state["count"] + 1, "log": ["step_a ran"]}


def step_b(state: ToyState) -> dict:
    return {"count": state["count"] + 10, "log": state["log"] + ["step_b ran"]}


g = StateGraph(ToyState)      # 1. make a graph, tell it the state shape
g.add_node("a", step_a)       # 2. register each function as a station
g.add_node("b", step_b)
g.add_edge(START, "a")        # 3. wire the line: START → a → b → END
g.add_edge("a", "b")
g.add_edge("b", END)

app = g.compile()             # 4. freeze into a runnable object

if __name__ == "__main__":
    result = app.invoke({"count": 0, "log": []})   # 5. run once with seed state
    print(result)
