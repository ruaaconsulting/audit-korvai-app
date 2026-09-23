"""LLM helpers for the charter node.

Judgment lives here. Deterministic work lives in tools/:
skeleton extraction in tools/charter_brief.py, ratification checks in
tools/charter_validate.py. CharterProposal itself lives in state.py.
"""

from datetime import datetime

from audit_engine.state import CharterProposal
from audit_engine.config import get_model
from audit_engine.evals.jev_charter_judge import precheck_charter


CHARTER_PROMPT = """You are drafting a PMO Data Charter - the input contract for an audit.
You get skeleton structures extracted from the baseline standards: document names,
headings, and spreadsheet columns. Draft the charter as JSON.

Rules:
- proposed_artifact_ids: one ART-xxx id per baseline document (ART-001, ART-002, ...).
  Every id unique. Every baseline document gets one - no orphans.
- charter_metadata.organization: write "TBD" unless a baseline document names the
  organization. Never invent one.
- charter_metadata.charter_version: "1.0". audit_scope: the delivery areas under
  audit, e.g. ["Projects", "PMO"].
- charter_metadata.ratified_by: "TBD". charter_metadata.ratified_date: "1970-01-01".
  The human fills these at ratification - never invent a name or date.
- charter_metadata.charter_status: "PROVISIONAL".
- field_semantics_map: one entry per meaningful spreadsheet column or data field in
  the skeletons. field_name is the exact column/heading text. type is one of
  String, Date, Number, Enum, Boolean, Calculated. meaning is one plain sentence.
  nullability is NOT NULL or NULLABLE. business_rule states the checkable rule.
  standard_mapping names the standard and clause it came from. No invented fields -
  every field must trace to the skeletons below.
- materiality_scope: lookback_period like "12 months". Every threshold carries an
  explicit unit: field_completeness_threshold_pct as a number 0-100,
  max_artifact_age_days as a whole number of days, budget/schedule variance
  thresholds as percents. Skip any threshold the skeletons don't support.
- waivers: leave empty unless a skeleton clearly marks an artifact out of scope.
  Never invent a waiver.

SKELETONS:
{skeleton_brief}"""


def propose_charter(brief: str) -> tuple[CharterProposal, dict]:
    llm = get_model()
    structured = llm.with_structured_output(CharterProposal)
    proposal, check = None, {}
    for attempt in range(2):
        proposal = structured.invoke(CHARTER_PROMPT.format(skeleton_brief=brief))
        proposal.charter_metadata.proposal_date = datetime.now().strftime("%Y-%m-%d")
        check = precheck_charter(proposal.model_dump(mode="json"), brief)
        if all(check[k] >= 0.7 for k in ("coverage", "grounded_fields", "units")):
            break
        print(f"charter pre-check failed on attempt {attempt + 1} - redrafting")
    else:
        check["failed_after_retries"] = True
    return proposal, check
