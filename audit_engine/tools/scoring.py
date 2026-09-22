from typing import List
from audit_engine.state import Finding, ArtifactExamined, ReportingIntegrityScore, ScoreComponents, GapType

def compute_reporting_integrity_score(findings: List[Finding], artifacts: List[ArtifactExamined]) -> ReportingIntegrityScore:
    limitations = [
        "This score has not been calibrated across multiple organizations or decision types.",
        "Severity is assigned by LLM judgment (Stage 6) and is not empirically derived.",
        "A score from one audit is not directly comparable to another unless scope, standards, and materiality are identical.",
        "The score describes evidence state at a point in time; it does not predict outcomes."
    ]

    if not findings:
        return ReportingIntegrityScore(
            score=100.0, methodology="Weighted Gap Profile v1.2.0", version="1.2.0",
            components=ScoreComponents(
                severity_deduction=0, density_deduction=0, diversity_deduction=0,
                missing_deduction=0, total_findings=0,
                total_artifacts=max(len(artifacts), 1), unique_origins=0
            ),
            limitations=limitations
        )

    total_severity = sum(f.severity for f in findings)
    severity_deduction = min(total_severity, 50)

    art_count = max(len(artifacts), 1)
    density = len(findings) / art_count
    density_deduction = min(density * 5, 20)

    origins = {f.root_origin for f in findings}    # enum members - hashable, dedupes fine
    diversity_deduction = 10 if len(origins) > 4 else 0

    missing_count = sum(1 for f in findings if f.gap_type == GapType.MISSING)
    missing_deduction = min(missing_count * 3, 20)

    score = max(0.0, 100.0 - severity_deduction - density_deduction - diversity_deduction - missing_deduction)

    return ReportingIntegrityScore(
        score=round(score, 2), methodology="Weighted Gap Profile v1.2.0", version="1.2.0",
        components=ScoreComponents(
            severity_deduction=severity_deduction,
            density_deduction=round(density_deduction, 2),
            diversity_deduction=diversity_deduction,
            missing_deduction=missing_deduction,
            total_findings=len(findings), total_artifacts=art_count,
            unique_origins=len(origins)
        ),
        limitations=limitations
    )