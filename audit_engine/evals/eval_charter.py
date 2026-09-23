"""LangSmith evaluation for the charter proposal (pre-human half).

The charter node interrupts for human ratification, which cannot run
unattended - so this experiment targets propose_charter(), the LLM-draft +
Jev-precheck half. The human half is evaluated by inspection in the
LangSmith trace of a real run.

Dataset : korvai-charter-proposal-v1
Target  : propose_charter wrapped as dict-in/dict-out
Judge   : Jev (jev_charter_judge) + artifact recall vs the baseline index

Run: uv run python -m audit_engine.evals.eval_charter
"""
from langsmith import Client

from audit_engine.graph import propose_charter, skeleton_brief

client = Client()  # reads LANGSMITH_API_KEY
DATASET = "korvai-charter-proposal-v1"


def ensure_dataset() -> None:
    try:
        ds = client.create_dataset(
            DATASET, description="Charter proposal quality (pre-human)"
        )
    except Exception:
        ds = None  # already exists - reuse it
    if ds is not None:
        client.create_example(
            inputs={"run_label": "knowledge/ snapshot 2026-09-23"},
            outputs={"expected_artifact_ids": []},  # fill after first run
            dataset_id=ds.id,
        )


def charter_target(inputs: dict) -> dict:
    proposal, precheck = propose_charter(skeleton_brief())
    return {
        "charter": proposal.model_dump(mode="json"),
        "jev_precheck": precheck,
    }


def jev_charter_evaluator(inputs: dict, outputs: dict,
                          reference_outputs: dict) -> dict:
    pre = outputs.get("jev_precheck", {})
    scores = [
        pre.get("coverage", 0.0),
        pre.get("grounded_fields", 0.0),
        pre.get("units", 0.0),
    ]
    jev_mean = sum(scores) / len(scores)
    expected = (reference_outputs or {}).get("expected_artifact_ids", [])
    proposed = outputs.get("charter", {}).get("proposed_artifact_ids", [])
    recall = (
        len(set(expected) & set(proposed)) / len(expected) if expected else 1.0
    )
    return {
        "key": "charter_proposal_quality",
        "score": 0.7 * jev_mean + 0.3 * recall,
        "comment": f"jev={jev_mean:.2f} recall={recall:.2f} "
                   f"model={pre.get('model', 'jev')}",
    }


if __name__ == "__main__":
    ensure_dataset()
    results = client.evaluate(
        charter_target,
        data=DATASET,
        evaluators=[jev_charter_evaluator],
        experiment_prefix="charter-proposal",
    )
    print(results)
