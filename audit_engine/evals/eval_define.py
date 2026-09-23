"""LangSmith evaluation for the define node.

Dataset : korvai-define-registry-v1
Target  : define_node wrapped as dict-in/dict-out
Judge   : Jev (jev_define_judge), three typed questions per registry item

Run: uv run python -m audit_engine.evals.eval_define
"""
from langsmith import Client

from audit_engine.state import AuditState
from audit_engine.graph import define_node
from audit_engine.tools.baseline_text import load_baseline_text
from audit_engine.evals.jev_define_judge import grade_registry_item

client = Client()  # reads LANGSMITH_API_KEY
DATASET = "korvai-define-registry-v1"


def ensure_dataset() -> None:
    try:
        ds = client.create_dataset(
            DATASET, description="Define-node registry quality"
        )
    except Exception:
        ds = None  # already exists - reuse it
    if ds is not None:
        client.create_example(
            inputs={"run_label": "knowledge/ snapshot 2026-09-23"},
            outputs={"expected_criterion_ids": []},  # fill after first run
            dataset_id=ds.id,
        )


def define_target(inputs: dict) -> dict:
    out = define_node(AuditState())
    return {"registry": [i.model_dump() for i in out.get("registry", [])]}


def jev_define_evaluator(inputs: dict, outputs: dict,
                         reference_outputs: dict) -> dict:
    items = outputs.get("registry", [])
    if not items:
        return {"key": "define_registry_quality", "score": 0.0,
                "comment": "define node produced no registry items"}
    baseline = load_baseline_text()[:8000]
    probs = []
    model = "jev"
    for item in items:
        g = grade_registry_item(item, baseline)
        model = g["model"]
        probs.append(min(g["faithful"], g["grounded"], g["checkable"]))
    return {"key": "define_registry_quality",
            "score": sum(probs) / len(probs),
            "comment": f"{len(items)} items judged by {model}"}


if __name__ == "__main__":
    ensure_dataset()
    results = client.evaluate(
        define_target,
        data=DATASET,
        evaluators=[jev_define_evaluator],
        experiment_prefix="define-node",
    )
    print(results)
