"""LangSmith evaluation for the measure node.

Dataset : korvai-measure-evidence-v1
Target  : measure_node over a fixed synthetic criteria set, dict-in/dict-out
Judge   : Jev (jev_measure_judge) plus the deterministic verbatim check

Run: uv run python -m audit_engine.evals.eval_measure
"""
from langsmith import Client

from audit_engine.state import AuditState, RegistryItem
from audit_engine.graph import measure_node
from audit_engine.tools.baseline_text import load_baseline_text
from audit_engine.tools.evidence_store import verify_verbatim
from audit_engine.evals.jev_measure_judge import grade_evidence_item

client = Client()  # reads LANGSMITH_API_KEY
DATASET = "korvai-measure-evidence-v1"

# Fixed synthetic criteria - the same input every run, so runs are comparable.
SYNTHETIC_CRITERIA = [
    {
        "criterion_id": "RISK-001",
        "standard": "PMBOK 8th Ed",
        "clause": "11.2",
        "paraphrase": "The project maintains a risk register with named owners.",
        "expected_evidence": "Risk register listing each risk with owner and date",
    },
    {
        "criterion_id": "RISK-002",
        "standard": "PMBOK 8th Ed",
        "clause": "11.3",
        "paraphrase": "Qualitative risk analysis prioritizes risks by probability and impact.",
        "expected_evidence": "Probability-impact matrix with scored risks",
    },
    {
        "criterion_id": "SCHED-001",
        "standard": "PMBOK 8th Ed",
        "clause": "6.5",
        "paraphrase": "The project maintains a baseline schedule under change control.",
        "expected_evidence": "Approved baseline schedule with change log",
    },
]


def ensure_dataset() -> None:
    try:
        ds = client.create_dataset(
            DATASET, description="Measure-node evidence quality"
        )
    except Exception:
        ds = None  # already exists - reuse it
    if ds is not None:
        client.create_example(
            inputs={"criteria": SYNTHETIC_CRITERIA},
            outputs={"expected_criterion_ids": ["RISK-001", "RISK-002", "SCHED-001"]},
            dataset_id=ds.id,
        )


def measure_target(inputs: dict) -> dict:
    registry = [RegistryItem(**c) for c in inputs["criteria"]]
    out = measure_node(AuditState(registry=registry))
    evidence = out.get("evidence", [])
    return {
        "evidence": [
            e.model_dump(mode="json") if hasattr(e, "model_dump") else e
            for e in evidence
        ]
    }


def jev_measure_evaluator(inputs: dict, outputs: dict,
                         reference_outputs: dict) -> dict:
    records = outputs.get("evidence", [])
    found = [r for r in records if r.get("status") == "FOUND"]
    if not found:
        return {"key": "measure_evidence_quality", "score": 0.0,
                "comment": "measure node found no evidence"}
    baseline = load_baseline_text()[:8000]
    probs, model = [], "jev"
    for record in found:
        grades = grade_evidence_item(record, baseline)
        model = grades["model"]
        verbatim = 1.0 if verify_verbatim(record.get("excerpt", ""), baseline) else 0.0
        probs.append(min(verbatim, grades["supports"], grades["located"]))
    return {"key": "measure_evidence_quality",
            "score": sum(probs) / len(probs),
            "comment": (f"{len(found)}/{len(records)} records with evidence, "
                        f"judged by {model}")}


if __name__ == "__main__":
    ensure_dataset()
    results = client.evaluate(
        measure_target,
        data=DATASET,
        evaluators=[jev_measure_evaluator],
        experiment_prefix="measure-node",
    )
    print(results)
