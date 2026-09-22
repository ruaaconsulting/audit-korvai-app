# IEM-PM on the LangChain Ecosystem — Architecture Proposal

Date: 2026-09-17. Status: build approved 2026-09-17 — sequenced AFTER the 15-day sprint and Model Card Studio (Oct 30). No parallel builds.

**Naming (decided 2026-09-17):** IEM-PM is the methodology. **Korvai** is the brand (korvai.app). **Korvai Audit** is the first product — the IEM-PM engine rebuilt on the LangChain ecosystem. Future products (ParvAi, Aramai, Inaiyai…) ship under the same brand. Product home: `audit.korvai.app` (subdomain).

## What IEM-PM is today

IEM-PM (v1.15.0) is a Claude skill: `SKILL.md` + a `references/` knowledge base + deterministic Python scripts. An LLM does the judgment (read standards, read evidence, find gaps, classify into 7 gap types, trace to 7 root origins, assign severity 1–5, write the Audit Manifest). Python does the rest: validates the Manifest against a schema, converts it to canonical findings JSON, computes the Reporting Integrity Score (0–100), renders HTML/TXT reports.

The core design rule: **the Audit Manifest is the boundary between LLM judgment and deterministic software.** That rule survives the rebuild. LangChain orchestrates the judgment. Python keeps doing the math.

## Component mapping

| IEM-PM today | LangChain equivalent |
|---|---|
| Human reads artifacts from disk | Document loaders (CSV, Excel, PDF, Unstructured) → `Document` objects with source metadata (artifact id, sheet, page, cell) |
| Derive checkable registry from standards | LLM call with `with_structured_output(RegistryItem)` — Pydantic model: criterion id, standard name, clause, identifier, one-sentence paraphrase, expected evidence |
| Charter: machine-proposed → human-ratified | LangGraph `interrupt()` — graph proposes the Charter, pauses, human ratifies or edits, graph resumes |
| 8 thinking phases (baseline → evidence → measure → classify → trace → score → synthesize → handover) | LangGraph state machine — one node per phase, typed `AuditState` |
| Gap taxonomy with disambiguation examples | Few-shot prompt + structured output; the "test in order, stop at first match" rule becomes prompt instruction; gap type is a closed Python enum enforced at generation time |
| Validator (§10.3 rules) | A validation node that runs the existing Python validator; on failure, routes back to the failing node with the error message (self-correction loop) |
| `manifest_to_findings.py` + RIS + `render.py` | Plain Python functions called from graph nodes — not LLM work, unchanged |
| Severity 4/5 "Human Approved" field | LangGraph `interrupt()` before finalizing the Manifest |
| Stage references (`references/*.md`) | Injected into each node's system prompt (they are small and high-value); RAG over them is optional, not needed |

## The graph

Nodes: `baseline → propose_charter → [interrupt: ratify] → ingest → measure → classify → trace → score → synthesize → validate → [interrupt: approve sev 4/5] → compute → render`.

State (`AuditState`): charter, registry items, per-artifact evidence logs, findings list (each a `Finding` Pydantic object: gap type enum, root origin enum, evidence bullets, standard citation, severity, impact, recommended action, human-approved flag), manifest draft, validation errors.

Edges: linear with two loops. `validate → classify/synthesize` on schema failure (max 3 retries, then halt with the error). `validate → compute` on pass.

Every finding carries its evidence citations in state. Nothing reaches the Manifest without them.

## Where Deep Agents fits

A main audit agent with isolated subagents — one subagent per artifact (or per standard). Each subagent reads only its own artifact and returns an evidence log + candidate gaps.

This maps to IEM-PM's Principle 8 (Evidence Isolation): "only the evidence in the folder you were asked to audit is admissible." Subagent context isolation enforces mechanically what is today a judgment rule. A subagent cannot leak another artifact's content into its findings because it never sees it.

The main agent does measure/classify/trace/score/synthesize across the subagents' outputs. The filesystem holds per-artifact working memory.

## LangSmith: the audit trail of the audit

An evidence-assurance methodology that cannot show its own work is a contradiction. LangSmith tracing gives every classification decision a replayable trail: which evidence, which taxonomy rule, which severity calibration.

Evaluators to build (each maps to a real IEM-PM rule):

1. **Classification accuracy** — the master disambiguation examples (risk register × 7 situations) become a labeled eval dataset. The classifier must reproduce them.
2. **Evidence faithfulness** — every finding's evidence bullets must quote text actually present in the cited artifact. Test with a planted finding that cites fabricated evidence; the evaluator must catch it. (Same pattern as the Model Card Studio planted-lie test.)
3. **Copyright guard** — no finding's standard summary exceeds one sentence or contains verbatim standard text. Regex + LLM judge.
4. **Enum validity** — gap type and root origin ∈ closed sets. Deterministic check.
5. **No-duplicate rule** — no two findings share gap type + root origin + artifact + standard identifier. Deterministic check on the findings list.
6. **Charter discipline** — findings cite only artifacts declared in the Charter. Deterministic check.

Later, the LangSmith Engine loop applies directly: cluster recurring misclassifications in production audits → root-cause the prompt or taxonomy gap → propose the fix.

## What stays plain Python (not LangChain)

- Schema validation (`schema.py` logic)
- Manifest → findings JSON conversion
- Reporting Integrity Score computation
- HTML/TXT rendering
- Checksum comparison for prior audits

Same rule as Model Card Studio: deterministic math stays deterministic. The framework touches judgment, human checkpoints, and orchestration only.

## Design drivers (added 2026-09-17)

Three requirements from Ramani, plus Dr. Tony's assessment mapped to build items.

### 1. Model-agnostic

Today IEM-PM is a Claude skill — tied to one model family. The rebuild must run on any model.

- Every LLM call goes through LangChain's `BaseChatModel` interface, initialized with `init_chat_model()` from a single config value (`model="openai:gpt-4o"`, `"anthropic:claude-..."`, `"ollama:llama3.1"`, ...). Switching models is a config change, not a code change.
- No provider-specific features in prompts. Structured output via `with_structured_output()` everywhere — it works across providers (note: local models may need JSON-mode fallback; document the caveat).
- The Finding schema (Pydantic) is the contract, not prompt wording. If a model can't fill the schema, the validator rejects it the same way for every provider.
- Keep a tested-model matrix in the docs: which models the eval suite passes on, with scores. This doubles as Dr. Tony's Stage 2 "session/model sensitivity" test — model-agnosticism is what makes that test possible.

### 2. Platform-agnostic and shareable

Anyone online should be able to try it.

- Ship as a pip-installable package with a CLI: `iempm audit --evidence ./evidence --charter ./charter.md --model ollama:llama3.1`. One command, local run, no cloud required.
- Ship a Docker image for the no-setup path.
- Ship a **synthetic demo pack**: fake PMO artifacts (RAID log, schedule, governance pack) with planted gaps of every type. `iempm demo` runs a full audit on it. This is also the seeded-defect set for validation — the demo pack and the benchmark corpus are the same thing.
- Optional thin web UI (Streamlit or Gradio) for the try-it-in-browser path. It runs only the demo pack or user-uploaded files the user explicitly provides.
- LangSmith stays optional: tracing and evals activate only when an API key is present. Default run is local-only, honoring the local-first principle.

### 3. Enterprise extension (project → portfolio)

Today: one project, one evidence folder, one Manifest. Enterprise: many projects, one portfolio view.

- **Aggregation layer** (deterministic Python, not LLM): roll up findings across projects — counts by gap type and root origin, RIS distribution, repeat-offender patterns ("Ignored gaps with Tooling root origin appear in 5 of 8 projects").
- **Cross-project pattern detection**: an LLM synthesis step over aggregated findings only — never over raw evidence from another project (Principle 8 holds at enterprise scale: subagent isolation per engagement).
- **Hard boundaries, from Dr. Tony's release gates**: no cross-project score comparison until the measurement model is calibrated; no maturity modeling, ever — IEM-PM measures reporting integrity, not organizational maturity; no enterprise deployment without privacy, retention, and evidence-provenance controls.
- **Multi-tenancy**: evidence isolation per engagement is already the architecture (one subagent context per project). Add client authorization, retention/deletion controls, and data residency as config, not code changes.

### 4. Dr. Tony's recommendations → build items

Source: independent expert assessment, 14 Aug 2026. Positioning throughout: "AI-assisted evidence-assurance framework," not "validated methodology."

**Stage 1 — Construct validation.** The taxonomy's "closed and mutually exclusive" claim is asserted, not proven. One deliberate disagreement with Tony here, per Ramani's reply of 15 Aug 2026:
- **Single gap-type classification stays.** It is an action-forcing rule, not a claim that discrepancies have single causes: one finding → one type → one owner → one fix, so a PMO acts instead of debating causes. The taxonomy docs get rewritten to frame it this way, with documented boundary conditions and disambiguation tests for every boundary pair. The existing candidate-gap mechanism (Synthesis narrative) remains the escape hatch for observations that can't be evidenced — nothing is forced into the register without evidence.
- **Root origins: single accountable root + optional contributing factors**, each with confidence and evidence. Keeps one clear owner while recording the tangled reality Tony flagged.
- Build: boundary-test dataset from the taxonomy doc's own disambiguation traps (Missing↔Disconnected, Ignored↔Underutilized, etc.). The classification evaluator must reproduce the expected classifications.
- Tony's deeper suggestion — letting the engine mark findings as genuinely ambiguous instead of classifying — stays an open question. Ramani is working through it himself; no decision either way yet, and it is not built into the schema until he decides.

**Stage 2 — Technical validation.** Detection performance and reproducibility.
- Build: seeded-defect eval sets (the demo pack) with known gaps; precision/recall harness over classification, tracing, and severity.
- Build: model-sensitivity runs — same evidence evaluated multiple times: same model across sessions, different human reviewers, and across the model matrix (§1). Report consistency on all three axes: run-to-run, reviewer-to-reviewer, model-to-model.
- Build: provenance — cryptographic hashes of evidence files + immutable run IDs, logged as LangSmith run metadata alongside model, prompt, parameters, code version, and standard versions.

**Stage 3 — Professional validation.** Engine vs. qualified assessors.
- Build: blind-review mode — the HITL UI shows findings without revealing engine-vs-human origin; inter-rater agreement is computed and stored.
- Build: adjudication protocol — reviewer can approve, reject, or modify each finding; disagreements route to a documented adjudication step, not silent overwrite.

**Stage 4 — Business validation.** Decision and value impact.
- Build: **Decision Context layer** alongside the Charter — the decision being supported, accountable owner, materiality threshold, required evidence, freshness requirement, tolerated uncertainty. Tony's recommended enhancement, and it gives every finding a "so what."
- Build: corrective-action tracking — re-audits link findings to prior findings; closure and before/after state are recorded. This is what produces the "did it improve decisions" evidence.

**Transparent scoring.** Publish the RIS formula, severity weights, and denominator in the report itself. Replace two-decimal false precision with interpretation bands + confidence until calibration is demonstrated.

**Release gates as graph guards.** Encode Tony's gates as runtime checks: block cross-project comparison before calibration; block autonomous Major findings without human approval (already an interrupt); block enterprise mode without provenance controls configured.

## Expert feedback checklist (plain English)

Tick these off during development. Sources: Dr. Tony Prensa (assessment, 14 Aug 2026) and Dr. Brian (feedback, Sep 2026).

**What we call it**
- [ ] Say "AI-assisted evidence-assurance framework," not "validated methodology," until validation is done. (Tony)

**Taxonomy**
- [ ] One gap type per finding stays — it is the rule that forces one owner and one fix. Rewrite the taxonomy docs to say this plainly. (Ramani's decision, after Tony)
- [ ] Write boundary tests for every confusing pair (Missing vs Disconnected, Ignored vs Underutilized, etc.). The classifier must pass them. (Tony)
- [ ] Root origin: one accountable root plus optional contributing causes, each with a confidence level. (Ramani's decision, after Tony)
- [ ] If evidence can't support a finding, it goes to the Synthesis narrative as a candidate gap — never forced into the register. (existing rule; answers both experts)
- [ ] Do NOT build "mark as ambiguous / multiple classifications" until Ramani decides. Open question. (Ramani)

**Scoring**
- [ ] Publish the score formula, weights, and denominator inside the report itself. (Tony)
- [ ] Show the score as bands with confidence ("material limitations remain"), not two-decimal precision, until calibrated. (Tony)

**Human control**
- [ ] Severity 4/5 findings cannot finalize without a named human approving. Blocked without it. (Tony)
- [ ] Charter must be ratified by a human before the audit runs. (existing + Tony)
- [ ] Blind-review mode: reviewer sees findings without knowing engine-vs-human origin; track agreement. (Tony)
- [ ] Reviewer can approve, reject, or edit every finding; disagreements go to a documented adjudication step. (Tony)

**Trust and safety**
- [ ] Hash every evidence file; give every run an immutable ID. Log model, prompt, parameters, code version, and standard versions with each run. (Tony)
- [ ] Evidence files are data, never instructions. Flag suspected injected instructions in the report; never obey them. (Tony)
- [ ] Client controls: who can access data, how long it is kept, how it is deleted, where it lives. One engagement's evidence never leaks into another's. (Tony)

**Decision context (new)**
- [ ] Add a Decision Context layer next to the Charter: what decision this supports, who owns it, what counts as material, how fresh the evidence must be, what uncertainty is tolerated. (Tony)
- [ ] Track corrective actions across re-audits: which findings got fixed, what changed. This is how value gets proven later. (Tony)

**Validation tests to build**
- [ ] Seeded-defect demo pack: fake evidence with known gaps of every type; measure precision and recall. (Tony)
- [ ] Consistency test: same evidence, multiple runs, multiple reviewers, multiple models — report consistency on all three axes. (Tony + Brian)
- [ ] Classification accuracy test: the taxonomy's own worked examples must classify correctly. (Tony)

**Release gates (blockers, not warnings)**
- [ ] No "closed taxonomy" claim until boundary tests pass. (Tony)
- [ ] No comparing scores across projects until scoring is calibrated. (Tony)
- [ ] No enterprise mode without privacy, retention, and provenance controls in place. (Tony)
- [ ] No value claims ("better decisions") without measured before/after evidence. (Tony)

**What both experts liked — don't break**
- [ ] Keep: AI judges, code validates and scores. (Tony + Brian)
- [ ] Keep: No Evidence, No Finding. (Tony + Brian)
- [ ] Keep: gap type (what's wrong) separate from root origin (why). (Brian)

## Tensions to resolve before building

1. **Local-first vs. LangSmith cloud.** Principle 6 says runs are local, no cloud, evidence never leaves the machine. LangSmith tracing sends traces to LangSmith's cloud. Decide: self-hosted LangSmith, zero-retention option, or keep this build's traces local-only and use LangSmith only for eval datasets. Do not hand-wave this — it is the methodology's own trust boundary.
2. **Evidence as prompt-injection surface.** §6.8 already discloses this risk: evidence artifacts can contain embedded instructions. In an agentic build the surface grows (tool outputs feeding the next node). Mitigations: evidence text is always data, never instructions; subagent isolation limits blast radius; log and flag suspected injections in the Synthesis narrative. There is no complete technical fix — say so in the docs, as the skill already does.
3. **The skill's "no cloud APIs" principle** already bends (it runs on Claude). The rebuild makes the LLM dependency explicit. Fine — but the deterministic tail must keep working even if the model changes. Pydantic schemas, not prompt vibes, are the contract.

## Suggested sequencing

Design now (this document). The 0–90 day horizon from Dr. Tony's assessment (positioning, taxonomy rules, score formula disclosure, human-approval gates, security controls, whitepaper corrections → v1.2 spec + pilot protocol) runs in parallel with the LangChain sprint — it is writing and specification, not building.

Build right after the 15-day sprint, as the FIRST applied project — decided 2026-09-17. The whitepaper has been public since August, two expert reviews are in, and professionals need the tool for real-world testing; Korvai jumps ahead of Model Card Studio, which waits until Korvai's first public release. The build exercises everything the sprint teaches (structured output, LangGraph, HITL, LangSmith evals) on his own methodology, and the eval harness doubles as the Stage 1–2 validation instrument. No parallel builds.
