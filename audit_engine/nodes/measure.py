"""LLM helpers for the measure node.

Judgment lives here. Deterministic work lives in tools/:
excerpt fingerprinting, verbatim verification, and evidence storage in
tools/evidence_store.py. EvidenceRecord itself lives in state.py.
"""

from typing import List

from pydantic import BaseModel

from audit_engine.config import get_model
from audit_engine.state import EvidenceRecord
from audit_engine.evals.jev_measure_judge import precheck_evidence


class EvidenceList(BaseModel):
    """Local wrapper so the LLM returns a list of records as one object."""
    records: List[EvidenceRecord]


MEASURE_PROMPT = """You are collecting audit evidence - the factual basis for an audit.

For each criterion below, find the supporting evidence in the SOURCE TEXT and
record it. Rules:
- One record per criterion, in the same order, with the exact criterion_id given.
  No orphans, no extras.
- excerpt is an EXACT quote copied from the SOURCE TEXT. Never paraphrase, never
  summarize, never invent wording. If you cannot quote it exactly, it is not evidence.
- location names where the excerpt appears (section heading, clause, page).
- source_document is the document name as given in the source header.
- If the source contains no evidence for a criterion: status "NOT_FOUND",
  excerpt "", location "NOT_FOUND". Do not force a weak match - absence of
  evidence is itself a finding downstream.
- Never invent a document, section, or quote.

CRITERIA:
{criteria_brief}

SOURCE TEXT:
{source_text}"""


def _field(item, name: str):
    """Registry items are RegistryItem objects; tolerate dicts too."""
    if hasattr(item, name):
        return getattr(item, name)
    if isinstance(item, dict):
        return item.get(name, "")
    return ""


def _criteria_brief(registry: list) -> str:
    lines = []
    for item in registry:
        lines.append(
            f"{_field(item, 'criterion_id')} | {_field(item, 'paraphrase')} "
            f"| expected evidence: {_field(item, 'expected_evidence')}"
        )
    return "\n".join(lines)


def ensure_full_coverage(records: list, registry: list) -> list:
    """Deterministic repair: exactly one record per registry criterion.

    Any criterion the LLM dropped (or never attempted) gets a NOT_FOUND
    record; duplicate criterion_ids are de-duplicated (first wins); the
    result follows registry order. Never returns an empty list when the
    registry is non-empty. Raises RuntimeError on an empty registry
    instead of silently forwarding nothing downstream.
    """
    if not registry:
        raise RuntimeError(
            "measure: empty registry - cannot produce evidence records. "
            "Check that define_node derived criteria before measure ran."
        )
    paraphrases = {
        _field(r, "criterion_id"): _field(r, "paraphrase") for r in registry
    }
    seen = set()
    covered = []
    for rec in records or []:
        cid = rec.criterion_id
        if cid in seen:
            continue  # LLM extra - first occurrence wins
        seen.add(cid)
        covered.append(rec)
    for item in registry:
        cid = _field(item, "criterion_id")
        if cid and cid not in seen:
            seen.add(cid)
            covered.append(EvidenceRecord(
                criterion_id=cid,
                source_document="",
                location="NOT_FOUND",
                excerpt="",
                status="NOT_FOUND",
                criterion_paraphrase=paraphrases.get(cid, ""),
            ))
    order = {_field(r, "criterion_id"): i for i, r in enumerate(registry)}
    covered.sort(key=lambda r: order.get(r.criterion_id, 999))
    return covered


def propose_evidence(source_text: str, registry: list) -> tuple[list, dict]:
    """Draft evidence records for every registry criterion, Jev-checked.

    Returns (records, check). check carries verbatim/supports/located rates,
    found_rate, the judge model name, and failed_after_retries when both
    drafts failed the gate. records always has one entry per criterion
    (see ensure_full_coverage).
    """
    llm = get_model()
    structured = llm.with_structured_output(EvidenceList)
    brief = _criteria_brief(registry)
    paraphrases = {_field(r, "criterion_id"): _field(r, "paraphrase") for r in registry}

    records, check = None, {}
    for attempt in range(2):
        result = structured.invoke(
            MEASURE_PROMPT.format(criteria_brief=brief, source_text=source_text)
        )
        records = result.records
        # Backfill the criterion text deterministically - the LLM must not
        # rephrase what the evidence is for.
        for rec in records:
            rec.criterion_paraphrase = paraphrases.get(rec.criterion_id, "")
        check = precheck_evidence(
            [r.model_dump(mode="json") for r in records], source_text
        )
        if all(check[k] >= 0.7 for k in ("verbatim", "supports", "located")):
            break
        print(f"evidence pre-check failed on attempt {attempt + 1} - redrafting")
    else:
        check["failed_after_retries"] = True

    # Hard guard: one record per criterion, always. Never forward emptiness.
    records = ensure_full_coverage(records, registry)

    if check.get("found_rate", 0) == 0 and records:
        print("WARNING: no evidence found for any criterion - "
              "check the source text before running classify")

    return records, check
