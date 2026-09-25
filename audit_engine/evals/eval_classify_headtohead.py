"""Head-to-head: Jev vs Laya on the same classify eval set.

Runs the classify target once per backend over dataset korvai-classify-gap-v1.
The same two deterministic evaluators score both runs - no backend grades
itself, and the threshold code is shared, so the comparison is fair.

Run: uv run python -m audit_engine.evals.eval_classify_headtohead
Result: two experiments in LangSmith, `classify-jev-...` and
  `classify-laya-...`, side by side on detection + threshold discipline.

Notes:
- The Jev run needs TYPESAFE_API_KEY. The Laya run needs `pip install laya`;
  its first run downloads the 421M checkpoint from Hugging Face (slow once,
  then cached). Laya runs on CPU, just slower than on a GPU.
- Expect honestly: Laya is uncalibrated out of the box, so its verdicts will
  likely land in the human-review queue. That is the threshold code doing its
  job, and it is exactly what this experiment is for.
"""
from langsmith import Client

from audit_engine.state import AuditState, EvidenceRecord
from audit_engine.graph import classify_node

client = Client()  # reads LANGSMITH_API_KEY
DATASET = "korvai-classify-gap-v1"
BACKENDS = ("jev", "laya")

# Same fixed synthetic evidence for both backends - the input never changes,
# only the classifier does.
SYNTHETIC_EVIDENCE = [
    {
        "criterion_id": "RISK-001",
        "source_document": "synthetic-pmo-standard",
        "location": "NOT_FOUND",
        "excerpt": "",
        "status": "NOT_FOUND",
        "criterion_paraphrase": "The project maintains a risk register with named owners.",
    },
    {
        "criterion_id": "RISK-002",
        "source_document": "synthetic-pmo-standard",
        "location": "Section 4 - Risk",
        "excerpt": "The team talks about risks in the weekly meeting.",
        "status": "FOUND",
        "criterion_paraphrase": "Qualitative risk analysis prioritizes risks by probability and impact.",
    },
    {
        "criterion_id": "SCHED-001",
        "source_document": "synthetic-pmo-standard",
        "location": "Section 2 - Schedule",
        "excerpt": "The approved baseline schedule v3 is stored in the PMO repository; "
                   "changes require the change control board's sign-off.",
        "status": "FOUND",
        "criterion_paraphrase": "The project maintains a baseline schedule under change control.",
    },
]

# The only planted type we assert: a NOT_FOUND record is definitionally Missing.
EXPECTED = {"RISK-001": "Missing", "RISK-002": None}
VALID_TYPES = {"Missing", "Ignored", "Disconnected", "Untrusted",
               "Underutilized", "Misclassified", "Divergent"}


def ensure_dataset() -> None:
    try:
        ds = client.create_dataset(
            DATASET, description="Classify-node backend head-to-head"
        )
    except Exception:
        ds = None  # already exists - reuse it
    if ds is not None:
        client.create_example(
            inputs={"evidence": SYNTHETIC_EVIDENCE},
            outputs={"expected_gaps": EXPECTED},
            dataset_id=ds.id,
        )


def make_target(backend: str):
    """Target factory: the only thing that varies between runs is the
    backend string. classify_node reads it from the CLASSIFY_BACKEND env var
    (see graph.py)."""

    def classify_target(inputs: dict) -> dict:
        import os
        os.environ["CLASSIFY_BACKEND"] = backend
        evidence = [EvidenceRecord(**e) for e in inputs["evidence"]]
        out = classify_node(AuditState(evidence=evidence))
        verdicts = out.get("gap_verdicts", [])
        return {
            "verdicts": [
                v.model_dump(mode="json") if hasattr(v, "model_dump") else v
                for v in verdicts
            ],
            "check": out.get("classify_precheck", {}),
        }

    return classify_target


def detection_evaluator(inputs: dict, outputs: dict,
                        reference_outputs: dict) -> dict:
    """Did it find the planted gaps, with the right type where asserted?"""
    by_id = {v["criterion_id"]: v for v in outputs.get("verdicts", [])}
    expected = (reference_outputs or {}).get("expected_gaps", EXPECTED)
    hits, notes = 0, []
    for cid, expected_type in expected.items():
        v = by_id.get(cid, {})
        if v.get("verdict") != "GAP":
            notes.append(f"{cid}: missed (not a GAP)")
            continue
        if v.get("gap_type") not in VALID_TYPES:
            notes.append(f"{cid}: invalid type {v.get('gap_type')}")
            continue
        if expected_type and v.get("gap_type") != expected_type:
            notes.append(f"{cid}: type {v.get('gap_type')} != {expected_type}")
            continue
        hits += 1
        notes.append(f"{cid}: GAP/{v.get('gap_type')} "
                     f"P={v.get('type_confidence', 0):.2f}")
    sched = by_id.get("SCHED-001", {})
    if sched.get("verdict") != "SATISFIED":
        notes.append("SCHED-001: false positive (should be SATISFIED)")
    else:
        hits += 1
        notes.append("SCHED-001: correctly SATISFIED")
    total = len(expected) + 1
    return {"key": "classify_detection", "score": hits / total,
            "comment": "; ".join(notes)}


def threshold_discipline_evaluator(inputs: dict, outputs: dict,
                                   reference_outputs: dict) -> dict:
    """Step-3 code honesty, backend-agnostic: every GAP verdict below a
    threshold must be flagged for human review. A silent low-confidence
    verdict fails, whoever produced it."""
    check = outputs.get("check", {}) or {}
    thresholds = check.get("thresholds", {}) or {}
    class_t = thresholds.get("class", 0.7)
    bad = []
    for v in outputs.get("verdicts", []):
        if v.get("verdict") != "GAP":
            continue
        below = (v.get("type_confidence", 1) < class_t
                 or v.get("root_confidence", 1) < class_t)
        if below and not v.get("needs_human_review"):
            bad.append(v["criterion_id"])
    return {"key": "classify_threshold_discipline",
            "score": 1.0 if not bad else 0.0,
            "comment": ("all low-confidence verdicts flagged"
                        if not bad else f"unflagged: {bad}")}


if __name__ == "__main__":
    ensure_dataset()
    for backend in BACKENDS:
        print(f"=== backend: {backend} ===")
        results = client.evaluate(
            make_target(backend),
            data=DATASET,
            evaluators=[detection_evaluator, threshold_discipline_evaluator],
            experiment_prefix=f"classify-{backend}",
        )
        print(results)
