"""LangSmith evaluation for the trace node.

Dataset : korvai-trace-accountability-v1
Target  : trace_node over synthetic gap verdicts, dict-in/dict-out
Judge   : none - every evaluator is a deterministic check

What this proves
----------------
1. The accountable root origin is preserved exactly as classify decided it.
2. The gap type is never changed by trace.
3. The runner-up is preserved as a contributing-factor lead, never promoted
   to an official classification.
4. Every traced gap links back to its evidence.
5. Missing origins and satisfied criteria are routed correctly.

Run: uv run python -m audit_engine.evals.eval_trace
"""
from langsmith import Client

from audit_engine.state import (
    AuditState, EvidenceRecord, GapVerdict, RegistryItem,
)
from audit_engine.graph import trace_node

client = Client()  # reads LANGSMITH_API_KEY
DATASET = "korvai-trace-accountability-v1"

# Shared evidence + registry the synthetic verdicts link against.
SYNTHETIC_EVIDENCE = [
    {
        "criterion_id": "RISK-001",
        "source_document": "RiskPlan.pdf",
        "location": "Section 3 - Risk register",
        "excerpt": "The risk register lists twelve risks; owners are assigned for nine.",
        "status": "FOUND",
        "criterion_paraphrase": "The project maintains a risk register with named owners.",
    },
    {
        "criterion_id": "SCHED-001",
        "source_document": "Schedule.mpp",
        "location": "Baseline tab",
        "excerpt": "Baseline saved 2026-03-01; three revisions since, none re-baselined.",
        "status": "FOUND",
        "criterion_paraphrase": "The project maintains a baseline schedule under change control.",
    },
    {
        "criterion_id": "COMM-001",
        "source_document": "CommsPlan.pdf",
        "location": "NOT_FOUND",
        "excerpt": "",
        "status": "NOT_FOUND",
        "criterion_paraphrase": "The project communicates status to stakeholders on a fixed cadence.",
    },
]

SYNTHETIC_REGISTRY = [
    {
        "criterion_id": "RISK-001",
        "standard": "PMBOK 8th Ed",
        "clause": "11.2",
        "paraphrase": "The project maintains a risk register with named owners.",
        "expected_evidence": "Risk register listing each risk with owner and date",
    },
    {
        "criterion_id": "SCHED-001",
        "standard": "PMBOK 8th Ed",
        "clause": "6.5",
        "paraphrase": "The project maintains a baseline schedule under change control.",
        "expected_evidence": "Approved baseline schedule with change log",
    },
    {
        "criterion_id": "COMM-001",
        "standard": "PMBOK 8th Ed",
        "clause": "10.1",
        "paraphrase": "The project communicates status to stakeholders on a fixed cadence.",
        "expected_evidence": "Status reports issued on a fixed schedule",
    },
]

# One example per case. The verdict is the input; the outputs are the facts
# trace must preserve (never decide).
SYNTHETIC_EXAMPLES = [
    {
        "inputs": {
            "verdicts": [{
                "criterion_id": "RISK-001",
                "verdict": "GAP",
                "gap_type": "Missing",
                "gap_confidence": 0.91,
                "type_confidence": 0.78,
                "root_origin": "Capture",
                "root_confidence": 0.83,
                "considered_alternative": "Disconnected (P=0.31)",
                "needs_human_review": False,
                "review_reason": "",
                "criterion_paraphrase": "The project maintains a risk register with named owners.",
                "evidence_excerpt": "The risk register lists twelve risks; owners are assigned for nine.",
            }],
            "evidence": SYNTHETIC_EVIDENCE,
            "registry": SYNTHETIC_REGISTRY,
        },
        "outputs": {
            "expect_traced": True,
            "expected_origin": "Capture",
            "expected_type": "Missing",
            "runner_up_name": "Disconnected",
            "expect_missing_origin": False,
            "expect_evidence_linked": True,
        },
    },
    {
        "inputs": {
            "verdicts": [{
                "criterion_id": "SCHED-001",
                "verdict": "GAP",
                "gap_type": "Untrusted",
                "gap_confidence": 0.88,
                "type_confidence": 0.71,
                "root_origin": "Tooling",
                "root_confidence": 0.66,
                "considered_alternative": "Divergent (P=0.44)",
                "needs_human_review": False,
                "review_reason": "",
                "criterion_paraphrase": "The project maintains a baseline schedule under change control.",
                "evidence_excerpt": "Baseline saved 2026-03-01; three revisions since, none re-baselined.",
            }],
            "evidence": SYNTHETIC_EVIDENCE,
            "registry": SYNTHETIC_REGISTRY,
        },
        "outputs": {
            "expect_traced": True,
            "expected_origin": "Tooling",
            "expected_type": "Untrusted",
            "runner_up_name": "Divergent",
            "expect_missing_origin": False,
            "expect_evidence_linked": True,
        },
    },
    {
        # Classify returned a gap but no root origin: trace must flag it,
        # never invent the accountability.
        "inputs": {
            "verdicts": [{
                "criterion_id": "COMM-001",
                "verdict": "GAP",
                "gap_type": "Ignored",
                "gap_confidence": 0.95,
                "type_confidence": 0.69,
                "root_origin": None,
                "root_confidence": 0.0,
                "considered_alternative": "Missing (P=0.28)",
                "needs_human_review": False,
                "review_reason": "",
                "criterion_paraphrase": "The project communicates status to stakeholders on a fixed cadence.",
                "evidence_excerpt": "",
            }],
            "evidence": SYNTHETIC_EVIDENCE,
            "registry": SYNTHETIC_REGISTRY,
        },
        "outputs": {
            "expect_traced": True,
            "expected_origin": None,
            "expected_type": "Ignored",
            "runner_up_name": "Missing",
            "expect_missing_origin": True,
            "expect_evidence_linked": True,
        },
    },
    {
        # Satisfied criteria produce no traced gaps.
        "inputs": {
            "verdicts": [{
                "criterion_id": "RISK-001",
                "verdict": "SATISFIED",
                "gap_type": None,
                "gap_confidence": 0.12,
                "type_confidence": 0.0,
                "root_origin": None,
                "root_confidence": 0.0,
                "considered_alternative": "",
                "needs_human_review": False,
                "review_reason": "",
                "criterion_paraphrase": "The project maintains a risk register with named owners.",
                "evidence_excerpt": "The risk register lists twelve risks; owners are assigned for nine.",
            }],
            "evidence": SYNTHETIC_EVIDENCE,
            "registry": SYNTHETIC_REGISTRY,
        },
        "outputs": {
            "expect_traced": False,
            "expected_origin": None,
            "expected_type": None,
            "runner_up_name": "",
            "expect_missing_origin": False,
            "expect_evidence_linked": False,
        },
    },
]


def ensure_dataset():
    # read_dataset needs the keyword form; the positional form raises
    # "ValueError: Exactly one argument ... must be defined".
    try:
        return client.read_dataset(dataset_name=DATASET)
    except Exception:
        pass  # not found - create it below
    try:
        ds = client.create_dataset(
            DATASET, description="Trace-node accountability checks"
        )
    except Exception as create_err:
        # Possibly created concurrently elsewhere: try reading once more.
        # If that fails too, surface the ORIGINAL create error (e.g. a bad
        # API key) instead of masking it.
        try:
            return client.read_dataset(dataset_name=DATASET)
        except Exception:
            raise create_err
    for ex in SYNTHETIC_EXAMPLES:
        client.create_example(
            inputs=ex["inputs"],
            outputs=ex["outputs"],
            dataset_id=ds.id,
        )
    return ds


def trace_target(inputs: dict) -> dict:
    verdicts = [GapVerdict(**v) for v in inputs["verdicts"]]
    evidence = [EvidenceRecord(**e) for e in inputs["evidence"]]
    registry = [RegistryItem(**r) for r in inputs["registry"]]
    out = trace_node(
        AuditState(gap_verdicts=verdicts, evidence=evidence, registry=registry)
    )
    return {
        "traced_gaps": [
            t.model_dump(mode="json") for t in out.get("traced_gaps", [])
        ],
        "check": out.get("trace_precheck", {}),
    }


def _one_traced(outputs: dict):
    gaps = outputs.get("traced_gaps", [])
    return gaps[0] if gaps else None


def eval_origin_preserved(inputs, outputs, reference_outputs) -> dict:
    if not reference_outputs.get("expect_traced"):
        return {"key": "trace_origin_preserved", "score": 1.0,
                "comment": "no traced gap expected"}
    t = _one_traced(outputs)
    ok = t is not None and t.get("accountable_root_origin") == reference_outputs.get("expected_origin")
    return {"key": "trace_origin_preserved", "score": 1.0 if ok else 0.0,
            "comment": f"origin kept: {t.get('accountable_root_origin') if t else None}"}


def eval_type_unchanged(inputs, outputs, reference_outputs) -> dict:
    if not reference_outputs.get("expect_traced"):
        return {"key": "trace_type_unchanged", "score": 1.0,
                "comment": "no traced gap expected"}
    t = _one_traced(outputs)
    ok = t is not None and t.get("gap_type") == reference_outputs.get("expected_type")
    return {"key": "trace_type_unchanged", "score": 1.0 if ok else 0.0,
            "comment": f"type kept: {t.get('gap_type') if t else None}"}


def eval_runner_up_as_lead(inputs, outputs, reference_outputs) -> dict:
    runner = reference_outputs.get("runner_up_name") or ""
    if not reference_outputs.get("expect_traced") or not runner:
        return {"key": "trace_runner_up_as_lead", "score": 1.0,
                "comment": "no runner-up to preserve"}
    t = _one_traced(outputs)
    factors = " ".join(t.get("contributing_factors", [])) if t else ""
    preserved = runner in factors
    not_promoted = (
        t is not None
        and t.get("gap_type") != runner
        and t.get("accountable_root_origin") != runner
    )
    ok = preserved and not_promoted
    return {"key": "trace_runner_up_as_lead", "score": 1.0 if ok else 0.0,
            "comment": f"runner-up '{runner}' preserved as lead: {preserved}, "
                       f"not promoted: {not_promoted}"}


def eval_evidence_linked(inputs, outputs, reference_outputs) -> dict:
    if not reference_outputs.get("expect_evidence_linked"):
        return {"key": "trace_evidence_linked", "score": 1.0,
                "comment": "no link expected"}
    t = _one_traced(outputs)
    levels = [link.get("level") for link in (t.get("trace_chain", []) if t else [])]
    ok = "evidence" in levels and "criterion" in levels and "standard" in levels
    return {"key": "trace_evidence_linked", "score": 1.0 if ok else 0.0,
            "comment": f"chain levels: {levels}"}


def eval_review_routing(inputs, outputs, reference_outputs) -> dict:
    check = outputs.get("check", {})
    gaps = outputs.get("traced_gaps", [])
    if not reference_outputs.get("expect_traced"):
        ok = len(gaps) == 0
        return {"key": "trace_review_routing", "score": 1.0 if ok else 0.0,
                "comment": f"satisfied verdict traced {len(gaps)} gaps"}
    if reference_outputs.get("expect_missing_origin"):
        t = _one_traced(outputs)
        ok = (
            t is not None
            and t.get("accountable_root_origin") is None
            and t.get("needs_human_review") is True
            and t.get("finding_id") in check.get("missing_origin", [])
        )
        return {"key": "trace_review_routing", "score": 1.0 if ok else 0.0,
                "comment": "missing origin flagged for human, none invented"}
    ok = len(check.get("missing_origin", [])) == 0
    return {"key": "trace_review_routing", "score": 1.0 if ok else 0.0,
            "comment": "origins locked, none missing"}


if __name__ == "__main__":
    ensure_dataset()
    results = client.evaluate(
        trace_target,
        data=DATASET,
        evaluators=[
            eval_origin_preserved,
            eval_type_unchanged,
            eval_runner_up_as_lead,
            eval_evidence_linked,
            eval_review_routing,
        ],
        experiment_prefix="trace-node",
    )
    print(results)