"""Deterministic validation of the human-ratified charter.

Runs after the human ratifies - never before. Plain Python only:
no LLM, no LangChain imports.

Raises ValueError("CHARTER_REJECTED: ...") on any failure. The audit stops
until the human fixes the charter - a rejected charter never flows downstream.
"""
from datetime import datetime


def validate_ratified_charter(human_response: dict) -> dict:
    data = human_response.get("charter", human_response)
    errors = []

    md = data.get("charter_metadata") or {}
    if md.get("charter_status") not in ("RATIFIED", "PROVISIONAL"):
        errors.append("charter_status must be RATIFIED or PROVISIONAL")
    if not (md.get("ratified_by") or "").strip():
        errors.append("ratified_by is required - a bare flag is not an audit trail")
    try:
        datetime.strptime(md.get("ratified_date", ""), "%Y-%m-%d")
    except ValueError:
        errors.append("ratified_date must be YYYY-MM-DD")
    if not (md.get("audit_scope") or []):
        errors.append("audit_scope must name at least one scope area")

    for w in data.get("waivers", []) or []:
        if not (w.get("waived_by") or "").strip():
            errors.append(
                f"waiver for '{w.get('expected_artifact')}' is missing waived_by"
            )
        try:
            datetime.strptime(w.get("date", ""), "%Y-%m-%d")
        except ValueError:
            errors.append(
                f"waiver for '{w.get('expected_artifact')}' has bad date "
                "(want YYYY-MM-DD)"
            )

    ids = data.get("proposed_artifact_ids") or []
    if len(ids) != len(set(ids)):
        errors.append("proposed_artifact_ids must be unique")
    if not ids:
        errors.append("proposed_artifact_ids must name at least one artifact")

    if errors:
        raise ValueError("CHARTER_REJECTED: " + "; ".join(errors))
    return data
