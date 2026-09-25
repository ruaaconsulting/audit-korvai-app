"""
state.py

Unified Machine-Readable State for IEM-PM Audits.
Incorporates:
1. IEM-PM Canonical Findings v1.4.0 JSON Schema
2. PMO Data Charter (Input Contract)
3. Audit Manifest (Parser-Grade Intermediate Output Rules)

Requires: Pydantic >= 2.0
"""

import re
from datetime import datetime
from enum import Enum
from typing import List, Optional, Literal, Any

from pydantic import BaseModel, Field, field_validator, model_validator, ValidationError


# ==============================================================================
# 1. ENUMS (Case-Sensitive, matching Manifest & Schema exactly)
# ==============================================================================

class CharterStatus(str, Enum):
    RATIFIED = "RATIFIED"
    PROVISIONAL = "PROVISIONAL"

class ArtifactStatus(str, Enum):
    IN_SCOPE = "In Scope"
    WAIVED = "Waived"
    MISSING = "Missing"
    EXAMINED = "Examined"
    PARTIAL = "Partial"
    CORRUPTED = "Corrupted"
    EMPTY = "Empty"

class MaterialityLevel(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

class GapType(str, Enum):
    MISSING = "Missing"
    IGNORED = "Ignored"
    DISCONNECTED = "Disconnected"
    UNTRUSTED = "Untrusted"
    UNDERUTILIZED = "Underutilized"
    MISCLASSIFIED = "Misclassified"
    DIVERGENT = "Divergent"
    GAP_TYPE_DEFINITIONS = {
        "Missing": "The required artifact, data, or practice does not exist at all.",
        "Ignored": "It exists but is not used or followed in practice.",
        "Disconnected": "It exists but is not linked to the things that depend on it.",
        "Untrusted": "It exists but its accuracy or currency cannot be relied upon.",
        "Underutilized": "It exists and is trusted but its capability is not fully exploited.",
        "Misclassified": "It exists but is categorized or labeled in a way that misleads.",
        "Divergent": "Multiple versions or understandings exist and they disagree.",
    }

class RootOrigin(str, Enum):
    CAPTURE = "Capture"
    INTEGRATION = "Integration"
    DEFINITION_TAXONOMY = "Definition / Taxonomy"
    OWNERSHIP = "Ownership"
    PROCESS_CADENCE = "Process / Cadence"
    TOOLING = "Tooling"
    BEHAVIOR = "Behavior"

class IntelligenceDimension(str, Enum):
    VISIBILITY = "Visibility"
    INTEGRITY = "Integrity"
    CONNECTIVITY = "Connectivity"
    GOVERNANCE = "Governance"
    PREDICTABILITY = "Predictability"
    DECISION_QUALITY = "Decision Quality"
    CONTINUOUS_IMPROVEMENT = "Continuous Improvement"

# ==============================================================================
# 2. CHARTER MODELS (Input Contract)
# ==============================================================================

class CharterMetadata(BaseModel):
    organization: str
    charter_version: str
    audit_scope: List[str]  # e.g., ["Projects", "PMO"]
    ratified_by: str
    ratified_date: str  # YYYY-MM-DD
    charter_status: CharterStatus
    proposed_by: str = "IEM-PM Intelligence Engine"
    proposal_date: str  # YYYY-MM-DD

class Waiver(BaseModel):
    """1.2 Artifact Waivers: Only waived artifacts are out of scope."""
    standard_requirement: str
    expected_artifact: str
    waiver_reason: str
    waived_by: str
    date: str  # YYYY-MM-DD

class FieldSemantic(BaseModel):
    """2. Field Semantics Map: Defines what significant fields mean."""
    field_name: str
    type: str  # String, Date, Number, Enum, Boolean, Calculated
    meaning: str
    nullability: Literal["NOT NULL", "NULLABLE"]
    business_rule: str
    standard_mapping: str

class MaterialityScope(BaseModel):
    """3. Materiality and Scope: Boundaries derived from authoritative standards."""
    lookback_period: str
    min_project_value: Optional[str] = None
    budget_variance_threshold: Optional[str] = None
    schedule_variance_threshold: Optional[str] = None
    field_completeness_threshold_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    max_artifact_age_days: Optional[int] = None

class RegistryItem(BaseModel):
    criterion_id: str
    standard: str
    clause: Optional[str] = None
    paraphrase: str
    expected_evidence: str

class EvidenceRecord(BaseModel):
    criterion_id: str
    source_document: str
    location: str            # e.g. "Section 11.2" or "NOT_FOUND"
    excerpt: str             # verbatim quote; "" when NOT_FOUND
    status: str              # "FOUND" or "NOT_FOUND"
    criterion_paraphrase: str = ""  # backfilled deterministically from the registry
    fingerprint: str = ""    # sha256 of the excerpt, set by tools/evidence_store.py

class GapVerdict(BaseModel):
    criterion_id: str
    verdict: str  # "SATISFIED" or "GAP"
    gap_type: Optional[GapType] = None
    gap_confidence: float = 0.0      # P(this is a gap)
    type_confidence: float = 0.0     # P(chosen gap type)
    root_origin: Optional[RootOrigin] = None
    root_confidence: float = 0.0     # P(chosen root origin)
    considered_alternative: str = ""  # runner-up type + P; trace's lead
    needs_human_review: bool = False
    review_reason: str = ""
    criterion_paraphrase: str = ""  # copied from the evidence record
    evidence_excerpt: str = ""      # copied from the evidence record

class ScoredGap(BaseModel):
    finding_id: str = Field(..., pattern=r"^FIND-[0-9]{4}$")
    criterion_id: str
    gap_type: GapType
    accountable_root_origin: Optional[RootOrigin] = None
    severity: int = Field(..., ge=1, le=5)
    severity_parts: dict = Field(default_factory=dict)  # evidence/impact/scope/fix_at_source, each 1-5
    severity_rationale: str = ""
    requires_approval: bool = False  # True when severity >= 4
    gap_confidence: float = 0.0
    type_confidence: float = 0.0
    root_confidence: float = 0.0
    contributing_factors: List[str] = Field(default_factory=list)
    trace_chain: List[TraceLink] = Field(default_factory=list)
    needs_human_review: bool = False
    review_reason: str = ""
class TraceLink(BaseModel):
    level: str  # "criterion" | "evidence" | "standard"
    ref: str
    detail: str = ""
class TracedGap(BaseModel):
    finding_id: str = Field(..., pattern=r"^FIND-[0-9]{4}$")
    criterion_id: str
    gap_type: GapType  # carried through unchanged from the verdict
    accountable_root_origin: Optional[RootOrigin] = None  # exactly one when present
    gap_confidence: float = 0.0
    type_confidence: float = 0.0
    root_confidence: float = 0.0
    contributing_factors: List[str] = Field(default_factory=list)
    trace_chain: List[TraceLink] = Field(default_factory=list)
    needs_human_review: bool = False
    review_reason: str = ""
class CharterProposal(BaseModel):
    charter_metadata: CharterMetadata
    materiality_scope: MaterialityScope
    waivers: list[Waiver]
    field_semantics_map: list[FieldSemantic]
    proposed_artifact_ids: list[str]

    
# ==============================================================================
# 3. CANONICAL FINDINGS MODELS (Output State)
# ==============================================================================

class ArtifactExamined(BaseModel):
    """Combines Charter Artifact Declaration + Manifest Evidence Log requirements."""
    artifact_id: str = Field(
        ..., 
        pattern=r"^[A-Za-z0-9]{1,10}(-[A-Za-z0-9]{1,10}){1,3}$",
        description="PREFIX-SUFFIX ID scheme (e.g., ART-001, WK8-01, DOC-2026-08)"
    )
    artifact_name: str
    source_path: str
    format: str  # e.g., "MS Project / XML / XLSX"
    materiality: MaterialityLevel
    status: ArtifactStatus
    checksum: str = Field(
        ..., 
        description="Real SHA-256 of the artifact file. Never 'computed'."
    )
    field_coverage_pct: Optional[float] = Field(
        None, 
        ge=0.0, le=100.0, 
        description="Mandatory for parser: N of M declared columns present (X%)"
    )
    observations: Optional[str] = None

    @field_validator('checksum')
    @classmethod
    def validate_sha256(cls, v: str) -> str:
        """Manifest Rule: Compute real SHA-256, never write literal 'computed'."""
        if v.lower() == 'computed':
            raise ValueError("Checksum must be a real SHA-256 hash, not the literal word 'computed'.")
        if not re.match(r"^[a-fA-F0-9]{64}$", v):
            raise ValueError("Checksum must be a valid 64-character hexadecimal SHA-256 string.")
        return v


class EvidenceSummary(BaseModel):
    total_artifacts: int = Field(..., ge=0)
    total_fields_mapped: int = Field(..., ge=0)
    coverage_percentage: float = Field(..., ge=0.0, le=100.0)


class Evidence(BaseModel):
    artifact_id: str = Field(
        ..., 
        pattern=r"^[A-Za-z0-9]{1,10}(-[A-Za-z0-9]{1,10}){1,3}$"
    )
    location: str = Field(..., description="Sheet name, page, line, or cell reference")
    quote_or_absence: str = Field(..., description="Direct quote from artifact, or explicit statement of absence")


class StandardReference(BaseModel):
    standard: str = Field(..., description="e.g., PMBOK 8th Edition, Org PMM v2.3")
    clause: Optional[str] = Field(None, description="Clause or section reference")
    identifier: str = Field(..., description="Specific process ID or practice ID")
    summary: str = Field(
        ..., 
        max_length=200, 
        description="One-sentence paraphrase. Manifest Rule: Never reproduce full standard text."
    )


class Finding(BaseModel):
    id: str = Field(..., pattern=r"^FIND-[0-9]{4}$")
    gap_type: GapType
    root_origin: RootOrigin
    standard_reference: StandardReference
    
    description: str = Field(
        ..., 
        description="What you found and why it violates the standard."
    )
    severity: int = Field(..., ge=1, le=5, description="1=Cosmetic, 5=Critical delivery threat")
    
    # Manifest v1.2.0 / v1.3.0 Approval Gating
    human_approved: Optional[bool] = Field(None)
    human_approved_by: Optional[str] = Field(None)
    human_approved_at: Optional[str] = Field(None)
    
    impact: str = Field(..., description="Narrative impact on delivery capability")
    recommended_action: str = Field(..., description="Must address the root origin, not the symptom.")
    intelligence_dimensions: List[IntelligenceDimension]
    evidence: List[Evidence] = Field(..., min_length=1, description="Manifest Rule: Every finding must have at least one evidence bullet.")

    @field_validator('description')
    @classmethod
    def validate_description_length(cls, v: str) -> str:
        """Manifest Rule: Description must be at least 20 words."""
        word_count = len(v.split())
        if word_count < 20:
            raise ValueError(f"Description must be at least 20 words. Current count: {word_count}")
        return v

    @model_validator(mode='after')
    def validate_major_finding_approval(self):
        """
        Manifest Parser Rules Enforcement:
        - E-PARSE-008: Severity 4/5 without Human Approved is rejected.
        - E-PARSE-009: Human Approved: Yes without Approved By is rejected.
        """
        if self.severity in (4, 5):
            if self.human_approved is not True:
                raise ValueError("[E-PARSE-008] human_approved must be True for Severity 4 (Major) and 5 (Critical) findings.")
            if not self.human_approved_by or self.human_approved_by.strip() == "":
                raise ValueError("[E-PARSE-009] human_approved_by is required whenever human_approved is True. A bare flag is not an audit trail.")
            if not self.human_approved_at or self.human_approved_at.strip() == "":
                raise ValueError("[E-PARSE-009] human_approved_at is required whenever human_approved is True.")
        return self


class IntelligenceIndicators(BaseModel):
    """Manifest Synthesis Section: Narrative diagnostic labels only. Never scored."""
    visibility: str
    integrity: str
    connectivity: str
    governance: str
    predictability: str
    decision_quality: str
    continuous_improvement: str

    @field_validator('*')
    @classmethod
    def prevent_scoring_in_synthesis(cls, v: str) -> str:
        """Manifest Rule: Narrative diagnostic only. No scores, percentages, or grades."""
        if re.search(r'\b\d+%|\bscore\b|\bgrade\b|\b\d+\.\d+\b', v, re.IGNORECASE):
            raise ValueError("Synthesis fields must be narrative only. No scores, percentages, or grades allowed.")
        return v


class ScoreComponents(BaseModel):
    severity_deduction: float
    density_deduction: float
    diversity_deduction: float
    missing_deduction: float
    total_findings: int
    total_artifacts: int
    unique_origins: int


class ReportingIntegrityScore(BaseModel):
    score: float = Field(..., ge=0.0, le=100.0, description="Deterministic score based on gap profile")
    methodology: str
    version: str
    components: ScoreComponents
    limitations: List[str]


# ==============================================================================
# 4. ROOT MODEL (The Canonical State)
# ==============================================================================

class IEMPMCanonicalState(BaseModel):
    """
    Unified State Model combining Charter, Manifest, and Canonical Findings.
    This is the single source of truth generated after parsing the Manifest.
    """
    # --- Manifest Header / Charter Metadata ---
    audit_id: str = Field(..., pattern=r"^IEM-[0-9]{8}-[A-Z0-9]{6}$")
    charter_metadata: CharterMetadata
    schema_version: Literal["1.4.0"]
    skill_version: str = Field(..., description="Read directly from SKILL.md. Fallback: 'unknown'")
    model: str = Field(..., description="AI model actually running. Fallback: 'unknown'")
    generated_at: datetime
    
    # --- Baseline & Scope ---
    baseline_standards: List[str] = Field(..., min_length=1, description="Semicolon-separated in Manifest, list here.")
    materiality_scope: MaterialityScope
    waivers: List[Waiver] = Field(default_factory=list, description="Explicitly waived artifacts are out of scope.")
    
    # --- Evidence & Findings ---
    artifacts_examined: List[ArtifactExamined]
    field_semantics_map: List[FieldSemantic] = Field(default_factory=list, description="Ratified field definitions.")
    evidence_summary: EvidenceSummary
    findings: List[Finding]
    
    # --- Synthesis & Scoring ---
    intelligence_indicators: IntelligenceIndicators
    reporting_integrity_score: ReportingIntegrityScore

    @model_validator(mode='after')
    def validate_artifact_consistency(self):
        """
        Anti-Mirror Guard & Consistency Check:
        Ensure every evidence reference in findings points to an artifact 
        that was declared in the charter/artifacts_examined list.
        """
        valid_artifact_ids = {a.artifact_id for a in self.artifacts_examined}
        for finding in self.findings:
            for ev in finding.evidence:
                if ev.artifact_id not in valid_artifact_ids:
                    raise ValueError(
                        f"Evidence in {finding.id} references unknown artifact '{ev.artifact_id}'. "
                        "All evidence must reference an artifact declared in the Charter."
                    )
        return self

# ==============================================================================
# 5. GRAPH STATE (what LangGraph actually carries between nodes)
# ==============================================================================

class AuditState(BaseModel):
    """
    The mutable state LangGraph carries through the graph, one node at a
    time. Every field starts empty and fills in as the audit proceeds -
    unlike IEMPMCanonicalState above, nothing here is required, because
    state mid-audit is legitimately incomplete (there are no findings
    yet right after the baseline node runs, and that is correct, not
    an error).

    IEMPMCanonicalState stays exactly as it is: the schema for the
    completed, final output. This class is the new piece - the working
    copy nodes read from and write to on the way there.
    """

    # --- Filled by the baseline node (Stage 0) ---
    audit_id: Optional[str] = None
    baseline_standards: List[str] = Field(default_factory=list)

    # --- Filled by the charter node (Stage 1), after human ratification ---
    charter_metadata: Optional[CharterMetadata] = None
    materiality_scope: Optional[MaterialityScope] = None
    waivers: List[Waiver] = Field(default_factory=list)
    field_semantics_map: List[FieldSemantic] = Field(default_factory=list)

    # --- Filled by the evidence subagents / measure node ---
    artifacts_examined: List[ArtifactExamined] = Field(default_factory=list)
    evidence_summary: Optional[EvidenceSummary] = None

    # --- Filled by classify / trace / score / synthesize nodes ---
    registry: List[RegistryItem] = Field(default_factory=list)
    evidence: List[EvidenceRecord] = Field(default_factory=list)
    measure_precheck: dict = Field(default_factory=dict)
    gap_verdicts: List[GapVerdict] = Field(default_factory=list)
    classify_precheck: dict = Field(default_factory=dict)
    chartered_artifact_ids: List[str] = Field(default_factory=list)
    charter_proposal: dict = Field(default_factory=dict)
    charter_precheck: dict = Field(default_factory=dict)
    findings: List[Finding] = Field(default_factory=list)
    gap_verdicts: List[GapVerdict] = Field(default_factory=list)
    traced_gaps: List[TracedGap] = Field(default_factory=list)
    trace_precheck: dict = Field(default_factory=dict)
    scored_gaps: List[ScoredGap] = Field(default_factory=list)
    score_precheck: dict = Field(default_factory=dict)
    manifest_path: str = ""
    synthesize_precheck: dict = Field(default_factory=dict)
    classify_precheck: dict = Field(default_factory=dict)
    intelligence_indicators: Optional[IntelligenceIndicators] = None
    reporting_integrity_score: Optional[ReportingIntegrityScore] = None

    # --- Graph bookkeeping - has no equivalent in the old Manifest world ---
    validation_errors: List[str] = Field(default_factory=list)
    retry_count: int = 0
    schema_version: Literal["1.4.0"] = "1.4.0"
    skill_version: Optional[str] = None
    model: Optional[str] = None
    generated_at: Optional[datetime] = None

    def to_canonical(self) -> "IEMPMCanonicalState":
        """
        Call this once, in the final node, right before rendering.
        Raises pydantic.ValidationError if the audit is not actually
        complete yet - this is the real enforcement point for
        Contract 4, not a formality.
        """
        return IEMPMCanonicalState.model_validate(self.model_dump())

