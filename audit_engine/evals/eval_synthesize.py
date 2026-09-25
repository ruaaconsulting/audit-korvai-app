"""LangSmith evaluation for the synthesize node.

Dataset : korvai-synthesize-manifest-v1
Target  : synthesize_node over synthetic scored gaps, dict-in/dict-out
Judge   : none - every evaluator is a deterministic check

What this proves
----------------
1. Every finding has all canonical keys.
2. Every description is >= 20 words (canonical validation).
3. Evidence refs point at the right criterion with document + location.
4. Severity, confidence, gap type, and root origin are carried through
   unchanged - synthesize never re-scores or re-judges.
5. The Audit Manifest is written to disk as valid JSON with all findings.
6. The build is deterministic across runs.

Run: uv run python -m audit_engine.evals.eval_synthesize
"""
import json
import os
import tempfile

from langsmith import Client

from audit_engine.state import AuditState, EvidenceRecord, ScoredGap
from audit_engine.graph import synthesize_node

client = Client()  # reads LANGSMITH_API_KEY
DATASET = "korvai-synthesize-manifest-v1"

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
        "criterion_id": "COMM-001",
        "source_document": "CommsPlan.pdf",
        "location": "NOT_FOUND",
        "excerpt": "",
        "status": "NOT_FOUND",
        "criterion_paraphrase": "The project communicates status to stakeholders on a fixed cadence.",
    },
]


def _scored(finding_id, criterion_id, gap_type, origin, severity,
            rationale, gap_conf=0.9):
    return {
        "finding_id": finding_id,
        "criterion_id": criterion_id,
        "gap_type": gap_type,
        "accountable_root_origin": origin,
        "severity": severity,
        "severity_parts": {"evidence": 3, "impact": 4, "scope": 2,
                           "fix_at_source": 2},
        "severity_rationale": rationale,
        "requires_approval": severity >= 4,
        "gap_confidence": gap_conf,
        "type_confidence": 0.8,
        "root_confidence": 0.85,
        "contributing_factors": [],
        "trace_chain": [],
        "needs_human_review": False,
        "review_reason": "",
    }


SYNTHETIC_EXAMPLES = [
    {
        "inputs": {
            "scored_gaps": [
                _scored("FIND-0001", "RISK-001", "Missing", "Capture", 3,
                        "severity 3 = round_half_up(mean(evidence=3, impact=4, "
                        "scope=2, fix_at_source=2)=2.75)"),
                _scored("FIND-0002", "COMM-001", "Ignored", "Behavior", 5,
                        "severity 5 = round_half_up(mean(evidence=4, impact=5, "
                        "scope=4, fix_at_source=5)=4.50)"),
            ],
            "evidence": SYNTHETIC_EVIDENCE,
        },
        "outputs": {"expected_findings": 2},
    },
    {
        "inputs": {
            "scored_gaps": [
                _scored("FIND-0001", "COMM-001", "Ignored", "Behavior", 5,
                        "severity 5 = round_half_up(mean(evidence=4, impact=5, "
                        "scope=4, fix_at_source=5)=4.50)",
                        gap_conf=0.42),
            ],
            "evidence": SYNTHETIC_EVIDENCE,
        },
        "outputs": {"expected_findings": 1},
    },
    {
        "inputs": {
            "scored_gaps": [
                _scored("FIND-0001", "RISK-001", "Missing", "Capture", 3,
                        "severity 3 = round_half_up(mean(evidence=3, impact=4, "
                        "scope=2, fix_at_source=2)=2.75)"),
            ],
            "evidence": SYNTHETIC_EVIDENCE,
        },
        "outputs": {"expected_findings": 1},
    },
]

REQUIRED_KEYS = {
    "finding_id", "criterion_id", "gap_type", "accountable_root_origin",
    "severity", "confidence", "severity_rationale", "evidence_refs",
    "description", "impact", "recommended_action", "intelligence_dimensions",
}


def ensure_dataset():
    try:
        return client.read_dataset(dataset_name=DATASET)
    except Exception:
        pass  # not found - create it below
    try:
        ds = client.create_dataset(
            DATASET, description="Synthesize-node manifest checks"
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


def synthesize_target(inputs: dict) -> dict:
    scored = [ScoredGap(**s) for s in inputs["scored_gaps"]]
    evidence = [EvidenceRecord(**e) for e in inputs["evidence"]]
    state = AuditState(scored_gaps=scored, evidence=evidence)
    out = synthesize_node(state, manifest_dir=tempfile.mkdtemp(prefix="korvai_synth_"))
    return {
        "findings": out.get("findings", []),
        "manifest_path": out.get("manifest_path", ""),
        "check": out.get("synthesize_precheck", {}),
    }


def _findings(outputs):
    return outputs.get("findings", [])


def eval_keys_present(inputs, outputs, reference_outputs) -> dict:
    fs = _findings(outputs)
    expected = reference_outputs.get("expected_findings")
    ok = (len(fs) == expected and
          all(REQUIRED_KEYS <= set(f.keys()) for f in fs))
    return {"key": "synth_keys_present", "score": 1.0 if ok else 0.0,
            "comment": f"{len(fs)} findings, expected {expected}"}


def eval_description_length(inputs, outputs, reference_outputs) -> dict:
    fs = _findings(outputs)
    counts = [len(f.get("description", "").split()) for f in fs]
    ok = bool(fs) and all(c >= 20 for c in counts)
    return {"key": "synth_description_length", "score": 1.0 if ok else 0.0,
            "comment": f"word counts: {counts}"}


def eval_evidence_refs(inputs, outputs, reference_outputs) -> dict:
    fs = _findings(outputs)
    ok = True
    for f in fs:
        refs = f.get("evidence_refs", [])
        if not refs:
            ok = False
            break
        r = refs[0]
        ok = (r.get("criterion_id") == f.get("criterion_id")
              and bool(r.get("source_document"))
              and bool(r.get("location")))
        if not ok:
            break
    return {"key": "synth_evidence_refs", "score": 1.0 if ok else 0.0,
            "comment": "refs point at the finding's criterion" if ok
                       else "broken evidence ref"}


def eval_values_carried(inputs, outputs, reference_outputs) -> dict:
    fs = _findings(outputs)
    want = {s["finding_id"]: s for s in inputs["scored_gaps"]}
    ok = True
    for f in fs:
        s = want.get(f.get("finding_id"), {})
        if not (f.get("severity") == s.get("severity")
                and abs(f.get("confidence", -1) - s.get("gap_confidence", -2)) < 1e-9
                and f.get("gap_type") == s.get("gap_type")
                and f.get("accountable_root_origin") == s.get("accountable_root_origin")
                and f.get("severity_rationale") == s.get("severity_rationale")):
            ok = False
            break
    return {"key": "synth_values_carried", "score": 1.0 if ok else 0.0,
            "comment": "severity/confidence/type/origin/rationale unchanged"
                       if ok else "synthesize altered a scored value"}


def eval_manifest_written(inputs, outputs, reference_outputs) -> dict:
    path = outputs.get("manifest_path", "")
    try:
        with open(path, encoding="utf-8") as f:
            manifest = json.load(f)
        findings = manifest.get("findings", [])
        ok = (isinstance(findings, list)
              and len(findings) == reference_outputs.get("expected_findings")
              and all(REQUIRED_KEYS <= set(x.keys()) for x in findings))
        comment = f"manifest at {path}, {len(findings)} findings"
    except Exception as e:  # missing or invalid JSON
        ok, comment = False, f"manifest unreadable: {e}"
    return {"key": "synth_manifest_written", "score": 1.0 if ok else 0.0,
            "comment": comment}


def eval_deterministic(inputs, outputs, reference_outputs) -> dict:
    again = synthesize_target(inputs)
    f1, f2 = _findings(outputs), _findings(again)
    ok = len(f1) == len(f2) and all(
        a.get("description") == b.get("description")
        and a.get("recommended_action") == b.get("recommended_action")
        for a, b in zip(f1, f2)
    )
    return {"key": "synth_deterministic", "score": 1.0 if ok else 0.0,
            "comment": "identical findings across runs" if ok
                       else "non-deterministic synthesize detected"}


if __name__ == "__main__":
    ensure_dataset()
    results = client.evaluate(
        synthesize_target,
        data=DATASET,
        evaluators=[
            eval_keys_present,
            eval_description_length,
            eval_evidence_refs,
            eval_values_carried,
            eval_manifest_written,
            eval_deterministic,
        ],
        experiment_prefix="synthesize-node",
    )
    print(results)
