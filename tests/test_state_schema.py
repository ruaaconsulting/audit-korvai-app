"""
Quick close-out test for Phase 1.

Loads IEM-PM's real test_findings.json (from the GitHub repo's
scripts/ folder) into IEMPMCanonicalState. If this validates cleanly,
Phase 1's schema matches the real thing it was ported from.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from audit_engine.state import IEMPMCanonicalState
from pydantic import ValidationError

fixture_path = Path(__file__).parent / "fixtures" / "test_findings.json"
data = json.loads(fixture_path.read_text())

try:
    state = IEMPMCanonicalState.model_validate(data)
    print("PASS: test_findings.json validated cleanly against IEMPMCanonicalState.")
    print(f"  audit_id: {state.audit_id}")
    print(f"  findings: {len(state.findings)}")
    print(f"  score: {state.reporting_integrity_score.score}")
except ValidationError as e:
    print("FAIL: schema mismatch found. This is useful - it shows exactly")
    print("where state.py and the real IEM-PM output diverge.\n")
    print(e)

def test_findings_json_validates():
    fixture_path = Path(__file__).parent / "fixtures" / "test_findings.json"
    data = json.loads(fixture_path.read_text())
    state = IEMPMCanonicalState.model_validate(data)  # raises if invalid
    assert state.audit_id