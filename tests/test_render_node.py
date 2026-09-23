import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from datetime import datetime

from audit_engine.state import (
    AuditState, CharterMetadata, MaterialityScope, ArtifactExamined,
    EvidenceSummary, Finding, StandardReference, Evidence,
    IntelligenceIndicators, ReportingIntegrityScore, ScoreComponents,
    CharterStatus, ArtifactStatus, MaterialityLevel, GapType, RootOrigin,
    IntelligenceDimension,
)
from audit_engine.graph import findings_node, render_node

state = AuditState(
    audit_id="IEM-20260921-ABC123",
    schema_version="1.4.0",
    skill_version="1.15.0",
    model="claude-sonnet-4-6",
    generated_at=datetime.now(),
    baseline_standards=["PMBOK 8th Edition"],
    charter_metadata=CharterMetadata(
        organization="Korvai Test Org", charter_version="1.0",
        audit_scope=["Projects"], ratified_by="Ramani",
        ratified_date="2026-09-21", charter_status=CharterStatus.RATIFIED,
        proposal_date="2026-09-21",
    ),
    materiality_scope=MaterialityScope(lookback_period="90 days"),
    artifacts_examined=[ArtifactExamined(
        artifact_id="ART-001", artifact_name="RAID Log",
        source_path="/evidence/raid.xlsx", format="XLSX",
        materiality=MaterialityLevel.HIGH, status=ArtifactStatus.EXAMINED,
        checksum="a" * 64,
    )],
    evidence_summary=EvidenceSummary(
        total_artifacts=1, total_fields_mapped=10, coverage_percentage=90.0,
    ),
    findings=[Finding(
        id="FIND-0001", gap_type=GapType.MISSING, root_origin=RootOrigin.CAPTURE,
        standard_reference=StandardReference(
            standard="PMBOK 8th Edition", identifier="4.2",
            summary="Risk register must be maintained continuously.",
        ),
        description="The risk register has not been updated in over sixty days despite three new risks being verbally raised in status meetings.",
        severity=2,
        impact="Leadership cannot see current risk exposure.",
        recommended_action="Update risk register within five business days.",
        intelligence_dimensions=[IntelligenceDimension.VISIBILITY],
        evidence=[Evidence(
            artifact_id="ART-001", location="Sheet1!A1",
            quote_or_absence="No entries after 2026-07-01.",
        )],
    )],
    intelligence_indicators=IntelligenceIndicators(
        visibility="Risk visibility has degraded over the audit period.",
        integrity="Evidence is internally consistent where present.",
        connectivity="Risk data is not linked to the schedule.",
        governance="No recent governance review of risk items.",
        predictability="Insufficient data to assess forecast reliability.",
        decision_quality="Leadership lacks current risk information.",
        continuous_improvement="No corrective action tracked yet.",
    ),
    reporting_integrity_score=ReportingIntegrityScore(
        score=63.0, methodology="Deterministic gap-profile scoring", version="1.4.0",
        components=ScoreComponents(
            severity_deduction=10.0, density_deduction=5.0,
            diversity_deduction=2.0, missing_deduction=20.0,
            total_findings=1, total_artifacts=1, unique_origins=1,
        ),
        limitations=["Single-artifact test fixture, not representative."],
    ),
)

findings_node(state)
render_node(state)
first = Path("audit_engine/output/report.html").read_text()

findings_node(state)
render_node(state)
second = Path("audit_engine/output/report.html").read_text()

if first == second:
    print("PASS: byte-identical on re-render.")
else:
    print("FAIL: output differs between runs - this is a renderer defect per spec.")