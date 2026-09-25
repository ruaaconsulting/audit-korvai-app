"""Score node logic: assign severity via the four-part diagnostic. Deterministic.

severity = round_half_up(mean(evidence, impact, scope, fix_at_source)), clamped 1-5.

The four parts
--------------
- Evidence: how solid the proof of the gap is. FOUND with a verbatim quote
  -> 3. NOT_FOUND (the gap IS the absence of a required artifact) -> 4.
- Impact: inherent delivery impact of the gap type (stand-in table).
- Scope (Why/Who/Scope): how wide the root origin reaches (stand-in table).
- Fix-at-source: how hard the root origin is to fix at its source; harder
  to fix -> higher severity, because the delivery threat persists
  (stand-in table).

Confidence is a SEPARATE track (user decision 2026-09-25): it never changes
the severity number. Confidence only routes findings to human review, which
classify and trace already flag; score preserves those flags untouched.
Score adds one gate of its own: severity 4 or 5 requires named human
approval before the report goes out.

The stand-in tables below are v0.1 placeholders. They graduate to the
methodology skill (audit_engine/skills/iem_pm.py) when the real IEM-PM
methodology wording is finalized. No LangChain imports: pure deterministic
code.
"""

from audit_engine.state import ScoredGap

# --- v0.1 stand-in rubric (see module docstring) ---

TYPE_IMPACT = {
    "Missing": 4,
    "Ignored": 5,
    "Disconnected": 3,
    "Untrusted": 4,
    "Underutilized": 2,
    "Misclassified": 2,
    "Divergent": 3,
}

ORIGIN_SCOPE = {
    "Capture": 2,
    "Integration": 2,
    "Definition / Taxonomy": 3,
    "Ownership": 3,
    "Process / Cadence": 4,
    "Tooling": 2,
    "Behavior": 4,
}

ORIGIN_FIX_DIFFICULTY = {
    "Capture": 2,
    "Integration": 3,
    "Definition / Taxonomy": 3,
    "Ownership": 4,
    "Process / Cadence": 4,
    "Tooling": 2,
    "Behavior": 5,
}

EVIDENCE_PART = {"FOUND": 3, "NOT_FOUND": 4}

APPROVAL_THRESHOLD = 4  # severity >= 4 requires named human approval


def _field(obj, name, default=None):
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default


def _round_half_up(x: float) -> int:
    """Deterministic rounding: 2.5 -> 3 (unlike Python's banker's rounding)."""
    return int(x + 0.5)


def _enum_value(v) -> str:
    return v.value if hasattr(v, "value") else (v or "")


def score_gaps(traced_gaps: list, evidence: list) -> tuple[list, dict]:
    """Assign severity to every traced gap. Returns (scored_gaps, check)."""
    status_by_criterion: dict = {}
    for e in evidence or []:
        cid = _field(e, "criterion_id")
        status_by_criterion.setdefault(cid, _field(e, "status", ""))

    scored: list = []
    check = {
        "scored": 0,
        "unscored": [],
        "severity_histogram": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
        "approvals_needed": [],
        "needs_review": [],
        "evidence_unknown": [],
        "avg_severity": 0.0,
        "model": "deterministic",
    }

    for t in traced_gaps or []:
        gap_type = _enum_value(_field(t, "gap_type"))
        origin = _enum_value(_field(t, "accountable_root_origin"))
        finding_id = _field(t, "finding_id", "")
        cid = _field(t, "criterion_id", "")

        if not gap_type:
            # Trace guarantees a type; surface it if one ever arrives without.
            check["unscored"].append(finding_id or cid)
            continue

        status = status_by_criterion.get(cid, "")
        if status not in EVIDENCE_PART:
            check["evidence_unknown"].append(finding_id)
            status = "FOUND"  # conservative default, recorded in the check

        parts = {
            "evidence": EVIDENCE_PART[status],
            "impact": TYPE_IMPACT.get(gap_type, 3),
            "scope": ORIGIN_SCOPE.get(origin, 3),
            "fix_at_source": ORIGIN_FIX_DIFFICULTY.get(origin, 3),
        }
        mean = sum(parts.values()) / 4.0
        severity = min(5, max(1, _round_half_up(mean)))
        rationale = (
            f"severity {severity} = round_half_up(mean("
            f"evidence={parts['evidence']}, impact={parts['impact']}, "
            f"scope={parts['scope']}, fix_at_source={parts['fix_at_source']}"
            f")={mean:.2f})"
        )

        requires_approval = severity >= APPROVAL_THRESHOLD
        needs_review = bool(_field(t, "needs_human_review", False))
        review_reason = _field(t, "review_reason", "") or ""
        if requires_approval:
            needs_review = True
            review_reason = (
                (review_reason + "; " if review_reason else "")
                + f"severity {severity} requires named human approval"
            )
            check["approvals_needed"].append(finding_id)
        if needs_review:
            check["needs_review"].append(finding_id)

        check["severity_histogram"][str(severity)] += 1

        scored.append(ScoredGap(
            finding_id=finding_id,
            criterion_id=cid,
            gap_type=_field(t, "gap_type"),
            accountable_root_origin=_field(t, "accountable_root_origin"),
            severity=severity,
            severity_parts=parts,
            severity_rationale=rationale,
            requires_approval=requires_approval,
            gap_confidence=float(_field(t, "gap_confidence", 0.0) or 0.0),
            type_confidence=float(_field(t, "type_confidence", 0.0) or 0.0),
            root_confidence=float(_field(t, "root_confidence", 0.0) or 0.0),
            contributing_factors=list(_field(t, "contributing_factors", []) or []),
            trace_chain=list(_field(t, "trace_chain", []) or []),
            needs_human_review=needs_review,
            review_reason=review_reason,
        ))

    check["scored"] = len(scored)
    if scored:
        check["avg_severity"] = round(
            sum(s.severity for s in scored) / len(scored), 2
        )
    return scored, check
