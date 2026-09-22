# audit_engine/tools/render_helpers.py

def compute_origin_counts(findings):
    counts = {}
    for finding in findings:
        origin = finding.root_origin.value
        counts[origin] = counts.get(origin, 0) + 1
    return counts

def compute_severity_counts(findings):
    counts = {}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts