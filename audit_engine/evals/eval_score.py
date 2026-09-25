"""LangSmith evaluation for the score node.

Dataset : korvai-score-severity-v1
Target  : score_node over synthetic traced gaps, dict-in/dict-out
Judge   : none - every evaluator is a deterministic check

What this proves
----------------
1. Severity equals the hand-computed rubric value for each synthetic case.
2. All four diagnostic parts are recorded (1-5) with a rationale string.
3. Severity 4/5 triggers the named-human-approval gate.
4. Confidence never changes severity (the user's keep-separate decision,
   probed directly by re-running with boosted confidences).
5. Scoring is deterministic across runs.

Run: uv run python -m audit_engine.evals.eval_score
"""
import copy

from langsmith import Client

from audit_engine.state import AuditState, EvidenceRecord, TracedGap
from audit_engine.graph import score_node

client = Client()  # reads LANGSMITH_API_KEY
DATASET = "korvai-score-severity-v1"

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
    {
        "criterion_id": "QUAL-001",
        "source_document": "QualityLog.xlsx",
        "location": "NOT_FOUND",
        "excerpt": "",
        "status": "NOT_FOUND",
        "criterion_paraphrase": "The project logs quality defects with severity and owner.",
    },
]


def _traced(finding_id, criterion_id, gap_type, origin,
            gap_conf=0.9, type_conf=0.8, root_conf=0.85):
    return {
        "finding_id": finding_id,
        "criterion_id": criterion_id,
        "gap_type": gap_type,
        "accountable_root_origin": origin,
        "gap_confidence": gap_conf,
        "type_confidence": type_conf,
        "root_confidence": root_conf,
        "contributing_factors": [],
        "trace_chain": [],
        "needs_human_review": False,
        "review_reason": "",
    }


# Hand-computed from the v0.1 rubric in audit_engine/nodes/score.py:
# severity = round_half_up(mean(evidence, impact, scope, fix_at_source)).
SYNTHETIC_EXAMPLES = [
    {
        # evidence 3 (FOUND), impact 4 (Missing), scope 2 (Capture),
        # fix 2 (Capture) -> mean 2.75 -> 3. No approval.
        "inputs": {
            "traced_gaps": [_traced("FIND-0001", "RISK-001", "Missing", "Capture")],
            "evidence": SYNTHETIC_EVIDENCE,
        },
        "outputs": {"expected_severity": 3, "expected_approval": False,
                    "confidence_probe": False},
    },
    {
        # evidence 4 (NOT_FOUND), impact 5 (Ignored), scope 4 (Behavior),
        # fix 5 (Behavior) -> mean 4.5 -> 5. Approval required.
        "inputs": {
            "traced_gaps": [_traced("FIND-0001", "COMM-001", "Ignored", "Behavior")],
            "evidence": SYNTHETIC_EVIDENCE,
        },
        "outputs": {"expected_severity": 5, "expected_approval": True,
                    "confidence_probe": False},
    },
    {
        # evidence 3 (FOUND), impact 2 (Underutilized), scope 2 (Tooling),
        # fix 2 (Tooling) -> mean 2.25 -> 2. No approval.
        "inputs": {
            "traced_gaps": [_traced("FIND-0001", "SCHED-001", "Underutilized", "Tooling")],
            "evidence": SYNTHETIC_EVIDENCE,
        },
        "outputs": {"expected_severity": 2, "expected_approval": False,
                    "confidence_probe": False},
    },
    {
        # Same gap as case 1 but with collapsed confidences. Severity must
        # be identical: confidence never moves the number (keep-separate).
        "inputs": {
            "traced_gaps": [_traced("FIND-0001", "RISK-001", "Missing", "Capture",
                                    gap_conf=0.35, type_conf=0.30, root_conf=0.28)],
            "evidence": SYNTHETIC_EVIDENCE,
        },
        "outputs": {"expected_severity": 3, "expected_approval": False,
                    "confidence_probe": True},
    },
    {
        # evidence 4 (NOT_FOUND), impact 4 (Untrusted), scope 3 (Ownership),
        # fix 4 (Ownership) -> mean 3.75 -> 4. Approval required.
        "inputs": {
            "traced_gaps": [_traced("FIND-0001", "QUAL-001", "Untrusted", "Ownership")],
            "evidence": SYNTHETIC_EVIDENCE,
        },
        "outputs": {"expected_severity": 4, "expected_approval": True,
                    "confidence_probe": False},
    },
]


def ensure_dataset():
    try:
        return client.read_dataset(dataset_name=DATASET)
    except Exception:
        pass  # not found - create it below
    try:
        ds = client.create_dataset(
            DATASET, description="Score-node severity checks"
        )
    except Exception as create_err:
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


def score_target(inputs: dict) -> dict:
    traced = [TracedGap(**t) for t in inputs["traced_gaps"]]
    evidence = [EvidenceRecord(**e) for e in inputs["evidence"]]
    out = score_node(AuditState(traced_gaps=traced, evidence=evidence))
    return {
        "scored_gaps": [
            s.model_dump(mode="json") for s in out.get("scored_gaps", [])
        ],
        "check": out.get("score_precheck", {}),
    }


def _one_scored(outputs: dict):
    gaps = outputs.get("scored_gaps", [])
    return gaps[0] if gaps else None


def eval_severity_correct(inputs, outputs, reference_outputs) -> dict:
    s = _one_scored(outputs)
    expected = reference_outputs.get("expected_severity")
    ok = s is not None and s.get("severity") == expected
    return {"key": "score_severity_correct", "score": 1.0 if ok else 0.0,
            "comment": f"severity {s.get('severity') if s else None}, "
                       f"expected {expected}"}


def eval_parts_recorded(inputs, outputs, reference_outputs) -> dict:
    s = _one_scored(outputs)
    parts = (s.get("severity_parts", {}) if s else {})
    ok = (
        s is not None
        and set(parts.keys()) == {"evidence", "impact", "scope", "fix_at_source"}
        and all(isinstance(v, int) and 1 <= v <= 5 for v in parts.values())
        and bool(s.get("severity_rationale"))
    )
    return {"key": "score_parts_recorded", "score": 1.0 if ok else 0.0,
            "comment": f"parts: {parts}"}


def eval_approval_gating(inputs, outputs, reference_outputs) -> dict:
    s = _one_scored(outputs)
    expected_approval = bool(reference_outputs.get("expected_approval"))
    check = outputs.get("check", {})
    if s is None:
        return {"key": "score_approval_gating", "score": 0.0,
                "comment": "no scored gap"}
    gate_ok = s.get("requires_approval") == expected_approval
    reason_ok = (not expected_approval) or (
        "requires named human approval" in s.get("review_reason", "")
        and s.get("finding_id") in check.get("approvals_needed", [])
        and s.get("finding_id") in check.get("needs_review", [])
    )
    ok = gate_ok and reason_ok
    return {"key": "score_approval_gating", "score": 1.0 if ok else 0.0,
            "comment": f"severity {s.get('severity')}, approval "
                       f"{s.get('requires_approval')}, expected {expected_approval}"}


def eval_confidence_separate(inputs, outputs, reference_outputs) -> dict:
    if not reference_outputs.get("confidence_probe"):
        return {"key": "score_confidence_separate", "score": 1.0,
                "comment": "not the probe case"}
    boosted = copy.deepcopy(inputs)
    for t in boosted["traced_gaps"]:
        t["gap_confidence"] = 0.95
        t["type_confidence"] = 0.95
        t["root_confidence"] = 0.95
    again = score_target(boosted)
    s1 = _one_scored(outputs).get("severity")
    s2 = _one_scored(again).get("severity")
    ok = s1 == s2
    return {"key": "score_confidence_separate", "score": 1.0 if ok else 0.0,
            "comment": f"low-confidence severity {s1} vs "
                       f"high-confidence severity {s2}"}


def eval_deterministic(inputs, outputs, reference_outputs) -> dict:
    again = score_target(inputs)
    s1, s2 = _one_scored(outputs), _one_scored(again)
    ok = (
        s1 is not None and s2 is not None
        and s1.get("severity") == s2.get("severity")
        and s1.get("severity_parts") == s2.get("severity_parts")
        and s1.get("severity_rationale") == s2.get("severity_rationale")
    )
    return {"key": "score_deterministic", "score": 1.0 if ok else 0.0,
            "comment": "identical severity, parts, and rationale across runs"
                       if ok else "non-deterministic scoring detected"}


if __name__ == "__main__":
    ensure_dataset()
    results = client.evaluate(
        score_target,
        data=DATASET,
        evaluators=[
            eval_severity_correct,
            eval_parts_recorded,
            eval_approval_gating,
            eval_confidence_separate,
            eval_deterministic,
        ],
        experiment_prefix="score-node",
    )
    print(results)
