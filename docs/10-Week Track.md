# Compressed 10-Week Track

## 10-Week Phase Table

Same loop, same fixtures, same exit-criteria discipline as the 15-week plan - only the phase durations shrink, and two phases move out of the critical path entirely.

| Phase | Weeks | What changed vs. the 15-week plan | Exit criteria |
| --- | --- | --- | --- |
| 0. Foundations | 1 | Unchanged | Same as before |
| 1. State & Contracts | 1 | Unchanged - this phase is cheap and everything after it depends on getting it right | Same as before |
| 2. Graph skeleton | 1.5 | Weeks 3-4 merge into one 1.5-week block - Stages 0-10 stubbed and both interrupts wired without a separate integration week | Full stub graph runs end to end with both interrupts firing |
| 3. Deep Agents + Measure | 1.5 | Subagent delegation and the registry-deriver build in parallel instead of sequential weeks | Stage 3 still reproduces test\_manifest.md's two findings exactly |
| 4. Remaining judgment stages | 1.5 | Classify and Trace compress into fewer days now that skill-lookup is a familiar pattern from Phase 3 | Full pipeline still reproduces test\_findings.json's Reporting Integrity Score |
| 5. Observability + Evaluation | 1 | One dataset build session instead of two - build both taxonomy datasets and the regression dataset back to back | Baseline eval score recorded, same bar as before |
| 6. Sandboxes | Deferred | **Not in this track** - ships post-launch | See the trade-off note below |
| 7. LLM Gateway | 0.5 | Unchanged in substance, just 2-3 focused days rather than spread out | Same as before |
| 8. Deployment go-live | 1 | Onboard one tenant, skip the multi-restart durability drill until real usage demands it | audit.korvai.app live in staging with one real audit run start to finish |
| 9. Engine | 1 | Setup only, folded into the go-live week rather than its own slot | Engine is watching production traces from day one of staging |
| 10. Fleet + Context Hub | Deferred | **Not in this track** - ships post-launch | See the trade-off note below |

**Total: 10 weeks to a working, single-tenant audit.korvai.app in staging.**

## What This Trades Away

**Sandboxes (deferred).** SKILL.md section 6.8 already discloses that evidence parsing has an unsolved prompt-injection risk - a crafted PDF or spreadsheet could contain text trying to steer the analysis, and there is no automated defense yet. Running evidence parsing in-process for 10 weeks means that risk stays open a little longer, mitigated only by the trust-boundary middleware from Phase 2, not by microVM isolation. That is an acceptable trade only while every audit runs against evidence from a source you already trust - your own data, or a client you have a direct relationship with. It stops being acceptable the moment audit.korvai.app accepts evidence uploads from a party you cannot vouch for.

**Fleet + Context Hub (deferred).** No cost to correctness or security here - this is purely an adoption gap. Without it, every audit still has to be run by someone comfortable with Claude Code, the same way IEM-PM works today. Fine while you are the only user, or your users are all technical.

**When to stop deferring:** build Sandboxes before the first audit that touches evidence from an untrusted external source, and build Fleet before the first non-technical user needs to run an audit without you standing next to them. Neither is a fixed calendar date - they are triggered by who is about to use the product, not by a week number.
