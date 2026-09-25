"""Deterministic builders for the six canonical manifest fields.

The pipeline produces judgment (evidence, verdicts, gaps, scores,
findings). These six fields are facts about the run itself - version,
model, timestamp, and deterministic rollups - that nothing in the
pipeline sets today, which is why to_canonical() fails validation.

No LLM, no Jev, no LangChain imports. Called from findings_node right
before state.to_canonical().
"""

import os
from datetime import datetime, timezone

# Korvai Audit v0.1. Graduate with the methodology skill.
SKILL_VERSION = "0.1.0"


def _status(e) -> str:
    s = e.get("status") if isinstance(e, dict) else getattr(e, "status", "")
    return s.value if hasattr(s, "value") else (s or "")


def _gap_type(f) -> str:
    g = f.get("gap_type") if isinstance(f, dict) else getattr(f, "gap_type", "")
    return g.value if hasattr(g, "value") else (g or "")


def _severity(f) -> int:
    v = f.get("severity", 0) if isinstance(f, dict) else getattr(f, "severity", 0)
    return v or 0


def build_evidence_summary(evidence) -> dict:
    """EvidenceSummary as a plain dict (Pydantic parses it on validate).

    total_artifacts  = evidence records examined (one per criterion)
    total_fields_mapped = records with verbatim evidence (FOUND)
    coverage_percentage = 100 * mapped / total (0.0 when nothing examined)
    """
    total = len(evidence or [])
    found = sum(1 for e in (evidence or []) if _status(e) == "FOUND")
    coverage = round(100.0 * found / total, 1) if total else 0.0
    return {
        "total_artifacts": total,
        "total_fields_mapped": found,
        "coverage_percentage": coverage,
    }


def build_intelligence_indicators(findings, evidence) -> dict:
    """IntelligenceIndicators as a plain dict.

    v0.1 stand-in: narrative labels only, derived from the gap profile.
    The model forbids scores, percentages, and grades in these fields, so
    every label is a plain word (strong / adequate / weak / absent).
    Graduate the wording with the methodology skill.
    """
    types = {_gap_type(f) for f in (findings or [])}
    sev5 = any(_severity(f) >= 5 for f in (findings or []))
    cov = build_evidence_summary(evidence)["coverage_percentage"]

    if cov == 0:
        visibility = "absent"
    elif cov == 100 and "Missing" not in types:
        visibility = "strong"
    else:
        visibility = "weak"

    def weak_if(*gap_types):
        return "weak" if any(t in types for t in gap_types) else "adequate"

    return {
        "visibility": visibility,
        "integrity": weak_if("Untrusted"),
        "connectivity": weak_if("Disconnected"),
        "governance": "weak" if ("Ignored" in types or sev5) else "adequate",
        "predictability": weak_if("Divergent"),
        "decision_quality": weak_if("Misclassified"),
        "continuous_improvement": weak_if("Underutilized"),
    }


def build_reporting_integrity_score(findings, evidence):
    """Delegate to the existing deterministic scorer in tools/scoring.py."""
    from audit_engine.tools.scoring import compute_reporting_integrity_score
    from audit_engine.state import ReportingIntegrityScore

    ris = compute_reporting_integrity_score(findings or [], evidence or [])
    if not isinstance(ris, ReportingIntegrityScore):
        ris = ReportingIntegrityScore.model_validate(ris)
    return ris


def canonical_updates(state) -> dict:
    """The six fields to_canonical() requires, built deterministically."""
    evidence = getattr(state, "evidence", None) or []
    findings = getattr(state, "findings", None) or []
    return {
        "skill_version": SKILL_VERSION,
        "model": os.environ.get("KORVAI_MODEL", "unknown"),
        "generated_at": datetime.now(timezone.utc),
        "evidence_summary": build_evidence_summary(evidence),
        "intelligence_indicators": build_intelligence_indicators(
            findings, evidence),
        "reporting_integrity_score": build_reporting_integrity_score(
            findings, evidence),
    }
