"""Synthesize node logic: build canonical findings and write the Audit Manifest.

Deterministic: no LLM, no Jev. Synthesize assembles the human-readable
finding records from the scored gaps and writes the complete audit manifest
to disk. The manifest is the compaction-survival gate: everything before it
is LLM judgment, everything after is deterministic code.

A finding carries:
- description (>= 20 words): templated narrative; the template guarantees
  the word count so the canonical validation always holds.
- evidence_refs: the exact evidence behind the finding (criterion,
  document, location, excerpt).
- impact: templated delivery-impact narrative.
- recommended_action: templated per (gap type, root origin). v0.1 stand-in;
  graduates to the methodology skill with the real IEM-PM wording.
- intelligence_dimensions: v0.1 stand-in mapping from gap type; likewise
  graduates to the methodology skill.
- severity / confidence / severity_rationale: carried through untouched
  from the scored gap. Synthesize never re-scores and never re-judges.
"""

import json
import os
import time

# --- v0.1 stand-in content (see module docstring) ---

TYPE_ACTIONS = {
    "Missing": "Produce the missing artifact and record it where the project tracks this criterion.",
    "Ignored": "Escalate to the accountable owner and set a dated remediation commitment.",
    "Disconnected": "Link the existing artifacts so the criterion traces end to end.",
    "Untrusted": "Re-verify the artifact against its source and record the verification.",
    "Underutilized": "Put the existing artifact to its intended use or formally retire it.",
    "Misclassified": "Reclassify the artifact under the correct category and update the register.",
    "Divergent": "Reconcile the conflicting versions into one authoritative source.",
}

ORIGIN_ACTIONS = {
    "Capture": "Fix the capture step so the artifact is created at the source.",
    "Integration": "Fix the handoff between the tools or teams involved.",
    "Definition / Taxonomy": "Clarify the definition so everyone classifies the same way.",
    "Ownership": "Name a single accountable owner for this criterion.",
    "Process / Cadence": "Build the check into the operating cadence.",
    "Tooling": "Fix or replace the tool that should produce this artifact.",
    "Behavior": "Address the behavior directly with the people involved; process alone will not fix it.",
}

INTELLIGENCE_DIMENSIONS = {
    "Missing": ["completeness"],
    "Ignored": ["governance", "risk"],
    "Disconnected": ["traceability"],
    "Untrusted": ["assurance"],
    "Underutilized": ["value"],
    "Misclassified": ["taxonomy"],
    "Divergent": ["consistency"],
}


def _field(obj, name, default=None):
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default


def _enum_value(v) -> str:
    return v.value if hasattr(v, "value") else (v or "")


def _dump(obj):
    """JSON-safe dump of a Pydantic model, dict, or list."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _dump(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_dump(v) for v in obj]
    return obj


def _describe(scored, evidence) -> str:
    """Templated finding narrative. Always >= 20 words by construction."""
    finding_id = _field(scored, "finding_id", "")
    cid = _field(scored, "criterion_id", "")
    gap_type = _enum_value(_field(scored, "gap_type"))
    origin = _enum_value(_field(scored, "accountable_root_origin"))
    severity = _field(scored, "severity", 0)
    confidence = float(_field(scored, "gap_confidence", 0.0) or 0.0)
    rationale = _field(scored, "severity_rationale", "")
    paraphrase = _field(evidence, "criterion_paraphrase", "") or cid
    excerpt = (_field(evidence, "excerpt", "") or "").strip()
    doc = _field(evidence, "source_document", "") or "the reviewed documents"
    loc = _field(evidence, "location", "") or "location not recorded"

    if excerpt:
        evidence_sentence = (
            f'The evidence states: "{excerpt}" ({doc}, {loc}).'
        )
    else:
        evidence_sentence = (
            f"No evidence was found in {doc}, and the absence itself "
            f"is the finding ({loc})."
        )
    return (
        f"Finding {finding_id}: criterion {cid} ({paraphrase}) shows a "
        f"{gap_type} gap. {evidence_sentence} The accountable root origin "
        f"is {origin}, meaning the fix belongs there. Severity {severity} "
        f"of 5 ({rationale}). Confidence in this judgment is {confidence:.2f}."
    )


def build_findings(scored_gaps: list, evidence: list,
                   criteria: list = None) -> list:
    """Assemble one canonical finding dict per scored gap."""
    evidence_by_criterion = {}
    for e in evidence or []:
        evidence_by_criterion.setdefault(
            _field(e, "criterion_id"), e
        )

    findings = []
    for s in scored_gaps or []:
        cid = _field(s, "criterion_id", "")
        gap_type = _enum_value(_field(s, "gap_type"))
        origin = _enum_value(_field(s, "accountable_root_origin"))
        ev = evidence_by_criterion.get(cid)

        findings.append({
            "finding_id": _field(s, "finding_id", ""),
            "criterion_id": cid,
            "gap_type": gap_type,
            "accountable_root_origin": origin or None,
            "severity": _field(s, "severity", 0),
            "confidence": float(_field(s, "gap_confidence", 0.0) or 0.0),
            "severity_rationale": _field(s, "severity_rationale", ""),
            "evidence_refs": [{
                "criterion_id": cid,
                "source_document": _field(ev, "source_document", "") if ev else "",
                "location": _field(ev, "location", "") if ev else "",
                "excerpt": _field(ev, "excerpt", "") if ev else "",
            }] if ev is not None else [],
            "description": _describe(s, ev),
            "impact": (
                f"If left unaddressed, this {gap_type} gap (severity "
                f"{_field(s, 'severity', 0)}/5) weakens delivery assurance "
                f"for {cid}. The root cause sits at {origin}, so fixes "
                f"elsewhere will not hold."
            ),
            "recommended_action": (
                TYPE_ACTIONS.get(gap_type, "Investigate and remediate.") + " "
                + ORIGIN_ACTIONS.get(origin, "Assign an owner for the fix.")
            ),
            "intelligence_dimensions": list(
                INTELLIGENCE_DIMENSIONS.get(gap_type, ["general"])
            ),
        })
    return findings


def write_manifest(manifest: dict, directory: str = "manifests") -> str:
    """Write the complete Audit Manifest to disk. Returns the file path."""
    os.makedirs(directory, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(directory, f"audit_manifest_{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_dump(manifest), f, indent=2)
    return path
