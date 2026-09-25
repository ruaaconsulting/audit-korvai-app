"""Trace node logic: lock accountability, build the audit trail. Deterministic.

Trace never judges. Classify (Jev) already decided the gap type and the root
origin; trace takes both as given and assembles the accountable record:

- One TracedGap per GAP verdict, numbered FIND-0001, FIND-0002, ...
- accountable_root_origin = the verdict's root_origin, used exactly as Jev
  returned it. Exactly one per finding. Trace never re-asks, never overrides.
- gap_type carried through unchanged. Trace never reclassifies.
- contributing_factors: the runner-up from verdict.considered_alternative is
  preserved here as a lead ("Runner-up gap type: X (P=0.32) - lead only"),
  plus the evidence location. The runner-up is never promoted to an
  official classification.
- trace_chain: deterministic lineage criterion -> evidence -> standard.

Severity, impact, and narrative belong to score/synthesize, not trace.
No LangChain imports: this module is pure deterministic code.
"""

import re

from audit_engine.state import TracedGap, TraceLink

# Classify writes the runner-up as f"{name} (P={p:.2f})", e.g. "Disconnected (P=0.32)".
_RUNNER_UP_RE = re.compile(r"^(?P<name>.+?)\s+\(P=(?P<p>[0-9.]+)\)\s*$")


def _field(obj, name, default=None):
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default


def _parse_runner_up(considered_alternative: str):
    """Return (name, P) from 'Name (P=0.32)'; fall back to (raw string, None)."""
    raw = (considered_alternative or "").strip()
    if not raw:
        return None, None
    m = _RUNNER_UP_RE.match(raw)
    if m:
        try:
            return m.group("name").strip(), float(m.group("p"))
        except ValueError:
            pass
    return raw, None


def build_traces(gap_verdicts: list, evidence: list, registry: list) -> tuple[list, dict]:
    """Build one TracedGap per GAP verdict.

    Returns (traced_gaps, check). check is the deterministic pre-check dict
    the human interrupt reads; it flags missing origins, unlinked gaps,
    and anything needing review.
    """
    evidence_by_criterion: dict = {}
    for e in evidence or []:
        cid = _field(e, "criterion_id")
        evidence_by_criterion.setdefault(cid, []).append(e)
    registry_by_id: dict = {}
    for r in registry or []:
        cid = _field(r, "criterion_id")
        registry_by_id[cid] = r

    traced: list = []
    check = {
        "gaps_in": 0,
        "traced": 0,
        "types_unchanged": True,
        "origins_locked": 0,
        "missing_origin": [],
        "missing_type": [],
        "runner_ups_preserved": 0,
        "unlinked": [],
        "needs_review": [],
        "model": "deterministic",
    }

    n = 0
    for v in gap_verdicts or []:
        if _field(v, "verdict") != "GAP":
            continue
        check["gaps_in"] += 1
        cid = _field(v, "criterion_id", "")

        gap_type = _field(v, "gap_type")
        if gap_type is None:
            # A GAP verdict without a type is a classify bug: surface it,
            # never invent the type here.
            check["missing_type"].append(cid or f"verdict-{check['gaps_in']}")
            continue

        n += 1
        finding_id = f"FIND-{n:04d}"
        origin = _field(v, "root_origin")

        # Contributing factors: runner-up preserved as a lead, never promoted.
        factors: list = []
        runner_name, runner_p = _parse_runner_up(_field(v, "considered_alternative", ""))
        if runner_name:
            p_txt = f"P={runner_p:.2f}" if runner_p is not None else "P unknown"
            factors.append(
                f"Runner-up gap type: {runner_name} ({p_txt}) - lead only, "
                f"not the official classification"
            )
            check["runner_ups_preserved"] += 1

        # Deterministic lineage: criterion -> evidence -> standard.
        chain: list = []
        paraphrase = _field(v, "criterion_paraphrase", "") or ""
        chain.append(TraceLink(level="criterion", ref=cid, detail=paraphrase[:160]))
        ev_list = evidence_by_criterion.get(cid, [])
        if ev_list:
            e0 = ev_list[0]
            excerpt = _field(e0, "excerpt", "") or ""
            location = _field(e0, "location", "") or ""
            chain.append(TraceLink(
                level="evidence",
                ref=location or "location unknown",
                detail=excerpt[:160],
            ))
            if location:
                factors.append(f"Evidence location: {location}")
        reg = registry_by_id.get(cid)
        if reg is not None:
            std = _field(reg, "standard", "") or ""
            clause = _field(reg, "clause", "") or ""
            chain.append(TraceLink(
                level="standard",
                ref=f"{std} {clause}".strip(),
                detail=f"criterion {cid}",
            ))
        if not ev_list or reg is None:
            check["unlinked"].append(finding_id)

        needs_review = bool(_field(v, "needs_human_review", False))
        review_reason = _field(v, "review_reason", "") or ""
        if origin is None:
            # No accountable origin from classify: flag it, never invent one.
            check["missing_origin"].append(finding_id)
            needs_review = True
            review_reason = (
                (review_reason + "; " if review_reason else "")
                + "classify returned no root origin - human must assign accountability"
            )
        else:
            check["origins_locked"] += 1
        if needs_review:
            check["needs_review"].append(finding_id)

        traced.append(TracedGap(
            finding_id=finding_id,
            criterion_id=cid,
            gap_type=gap_type,
            accountable_root_origin=origin,
            gap_confidence=float(_field(v, "gap_confidence", 0.0) or 0.0),
            type_confidence=float(_field(v, "type_confidence", 0.0) or 0.0),
            root_confidence=float(_field(v, "root_confidence", 0.0) or 0.0),
            contributing_factors=factors,
            trace_chain=chain,
            needs_human_review=needs_review,
            review_reason=review_reason,
        ))

    check["traced"] = len(traced)
    return traced, check
