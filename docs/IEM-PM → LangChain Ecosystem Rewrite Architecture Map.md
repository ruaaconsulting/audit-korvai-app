# IEM-PM → LangChain Ecosystem Rewrite: Architecture Map

2026-09-17 · Prepared for @Someone · Target: **audit.korvai.app**

## Executive Summary

IEM-PM's own architecture is already structurally isomorphic to the LangChain ecosystem's product boundaries — this is not a translation exercise bolting a new framework onto old logic. Every major IEM-PM subsystem already has a purpose-built ecosystem product waiting for it:

- The **11-stage state machine** (audit-stages.md) → **LangGraph** — a stateful graph with durable execution and interrupts, instead of prose a human has to remember to follow.
- The **LLM-judgment work inside each stage** (reading standards, classifying gaps, tracing root origins, scoring) → **Deep Agents** — planning tools, isolated-context subagents, and a skills/memory filesystem.
- The **knowledge/ + registries/ pattern** → Deep Agents' native `skills/` (read-only) and `user/` (writable memory) tiers — this is close to a direct rename, not a redesign.
- The **deterministic Python pipeline** (schema.py, manifest\_to\_findings.py, render.py) → **Sandboxes** execution plus typed LangGraph state, which deletes the regex-parsing layer that caused two real production bugs (STATUS.md).
- The **hand-rolled timing.log, bug log, and regression suite** → **Observability**, **Evaluation**, and **Engine**.
- **Production hosting** for audit.korvai.app → **Deployment**.
- **Model/skill provenance**, currently hand-parsed from a Manifest header field → **LLM Gateway**.
- The **non-technical PM/PMO workflow** (setup wizards, copy-paste prompts in the User Guide) → **Fleet**.
- **Skill and taxonomy governance** as the reference library grows → **Context Hub**.

Every one of the ten ecosystem products below gets a real, load-bearing role in this design — none is included just to check a box.

## Ecosystem Product Glossary

| Product | Role in this design |
| --- | --- |
| **langchain** | Thin model/tool integration layer plus middleware hooks — enforces Read-Only and Evidence-Trust-Boundary as code, not just prompted rules |
| **langgraph** | Orchestration runtime — the 11-stage audit as a durable, resumable, interruptible graph |
| **deepagents** (Deep Agents SDK) | Agent harness for the judgment-heavy stages — planning tools, isolated-context subagents, skills/memory filesystem |
| **LangSmith Observability** | Tracing and monitoring — replaces timing.log with per-stage latency, cost, and trace clustering (Insights) |
| **LangSmith Evaluation** | Offline/online evals — turns the hand-written test fixtures and taxonomy disambiguation tables into real, versioned datasets |
| **LangSmith Engine** | Autonomous trace-analysis-to-fix — replaces the manual "found a bug via a live pilot audit, hand-wrote the fix, hand-updated STATUS.md" loop |
| **LangSmith Deployment** | Production runtime for audit.korvai.app — durable execution, the Charter-ratification human-in-the-loop pause, agent registry and versioning |
| **LangSmith Sandboxes** | Isolated microVM execution for parsing untrusted evidence files and running the deterministic render/scoring pipeline |
| **LangSmith LLM Gateway** | Centralized multi-provider model routing, spend/rate-limit policy, and automatic call provenance (skill\_version/model, currently hand-parsed) |
| **LangSmith Fleet** | No-code front door for non-technical PMs/PMO leads — replaces setup.bat/setup.sh/setup\_gui.pyw and the copy-paste-prompt workflow in the User Guide |
| **Context Hub** | Version control, review, and environment promotion for SKILL.md/references/taxonomies as the reference library and team grow |

## File-by-File Mapping

### Root-level & packaging

| IEM-PM path | Maps to | Reason |
| --- | --- | --- |
| `skills/intelligence-engine/SKILL.md` | Deep Agents `AGENTS.md` (always-loaded) + a `skills/audit-engine/SKILL.md` body | Already Agent-Skills-spec-shaped (name/description/version frontmatter) — Deep Agents loads this format natively. The always-binding parts (Operating Principles, Definitions, Cross-Cutting Rules) become AGENTS.md; the on-demand appendix content stays a skill body. |
| `.claude-plugin/plugin.json` | `deepagents.toml` | Same "declare identity + entry point" role, different host. |
| `requirements.txt` | `langgraph.json` dependencies + a Sandbox template image | Split in two: pure orchestration deps in langgraph.json; anything touching untrusted files (pypdf, openpyxl, cryptography) moves into a Sandbox image so a malformed file can't touch the orchestration host. |
| `setup.bat` / `setup.sh` / `setup.ps1` / `setup_gui.pyw` | A Fleet onboarding template | Fleet's whole pitch — template, connect accounts, no code — is a purpose-built replacement for the hand-rolled cross-platform installer wizard. |
| `build_release.py` | LangSmith Deployment's build/revision pipeline | Deployment already versions and packages an agent on every push; the maintainer-only allowlist-ZIP script becomes CI config. |
| `LICENSE`, `.gitignore`, `.gitattributes` | Unchanged | Plain repo hygiene — no ecosystem product needed. |

### knowledge/ + registries/

| IEM-PM path | Maps to | Reason |
| --- | --- | --- |
| `skills/intelligence-engine/knowledge/` | Deep Agents' `skills/` read-only tier, backed by a per-tenant retrieval store | The org's standards are exactly Deep Agents' "read-only at runtime" project-scoped skill tier. At audit.korvai.app's multi-tenant scale this becomes an indexed per-tenant document store behind a retrieval tool, not a literal folder. |
| `skills/intelligence-engine/registries/` (derived JSON) | Deep Agents' `user/` writable memory + LangGraph's long-term Store (semantic search) | Registries are memory derived from experience and reused across runs — the exact shape of Deep Agents' writable memory tier, backed by Deployment's Memory Store so it survives across sessions and tenants instead of living in a gitignored local folder. |
| `registry-format.md`'s on-demand derivation logic | A dedicated Deep Agents subagent (`registry-deriver`) | Deep-diving one PDF section on demand is bounded, parallelizable work that shouldn't pollute the main audit's context — exactly why Deep Agents isolates subagent work in its own context window. |

### SKILL.md's internal sections

| SKILL.md section | Maps to |
| --- | --- |
| §2 Operating Principles | AGENTS.md system prompt, plus langchain middleware enforcing Read-Only and Evidence Isolation as code, not just a prompted rule |
| §4 Five Contracts | The LangGraph typed State schema — each Contract becomes a schema field, not prose |
| §5 Thinking Phases / the 11 stages | The LangGraph graph itself — nodes = stages, conditional edges = Decision Logic, `interrupt()` = Halt Conditions |
| §6 Cross-Cutting Rules, esp. §6.8 Evidence Trust Boundary | A guardrail middleware that treats every evidence artifact as untrusted data — turns a disclosed, unsolved risk into an actual code-level defense |
| §6.9 Stage Timing Log | Deleted — LangSmith Observability gives per-node latency and cost for free |
| §9 Scoring | A deterministic tool node (plain Python, no LLM call) — same "code computes it" principle, running as a graph node instead of a standalone script |
| §10 Manifest Contract | The Synthesize node's structured-output schema — the LLM emits the Canonical Findings JSON directly; the free-text-Manifest-then-regex-parse step is retired |
| §13.4 Version (skill\_version/model) | LLM Gateway's centralized call logging — captured automatically instead of hand-parsed from a header field |

### scripts/ (deterministic pipeline)

| Script | Maps to | Reason |
| --- | --- | --- |
| `baseline.py` | A Stage-0 LangGraph node executed inside a Sandbox | PDF parsing is exactly the "run untrusted code safely" case Sandboxes exist for. |
| `derive_knowledge_index.py` | Folded into the same Stage-0 Sandbox node | SKILL.md already treats it as one Activity of Stage 0. |
| `paths.py` | Deleted | "Where do files live" stops being an application concern once Deployment manages per-tenant persistence. |
| `schema.py` | A Pydantic model on the graph edge + a standing LangSmith Evaluation schema-conformance evaluator | Same closed-taxonomy/no-duplicate/evidence-coverage checks, enforced as a typed edge condition and also run as a pre-deploy eval. |
| `manifest_to_findings.py` | **Deleted** | Its entire job — regex-parsing free-text Manifest markdown into JSON — disappears once Synthesize emits structured output directly. Two real production bugs (comma-splitting standard titles, "N of M" misread as a raw percentage) came specifically from this layer; structured output makes that bug class unrepresentable. |
| `render.py` / `render_scope_limitation.py` | LangGraph tool nodes, Sandbox-executed, same Jinja2 templates | Rendering logic is untouched — only its execution context changes. |
| `timing_log.py` | Deleted — LangSmith Observability | Direct replacement. |
| `findings.schema.json` | Becomes the LangGraph State's Pydantic schema directly | Single source of truth in code, not a parallel JSON Schema file. |
| `test_pipeline.py` + fixtures | LangSmith Evaluation dataset, run in CI | Already real regression tests against real fixtures — Evaluation adds experiment comparison across model/prompt versions instead of a binary pass/fail. |

### references/ (13 appendices)

| File | Maps to | Reason |
| --- | --- | --- |
| `gap-taxonomy.md`, `root-origins.md` | A Deep Agents skill body (loaded on demand, per §13.1's own rule) — **and** their worked disambiguation tables become LangSmith Evaluation dataset examples | Large reference, small trigger is exactly Deep Agents' skill-loading model; the worked examples are gold-labeled classification data, not just documentation. |
| `severity-matrix.md` | A deterministic lookup table inside the scoring tool node — not agent-read at all | It's pure arithmetic (Persistence × Spread × Decision Impact, banded); only picking the three input levels stays an LLM judgment call. |
| `scoring.md`, `terminology.md`, `charter-spec.md`, `evidence-sufficiency.md` | Deep Agents skill bodies, one file each | Each is a bounded, on-demand reasoning module. |
| `completion-checklist.md`, `report-generation.md` | Folded into the structured-output schema and a post-generation edge condition | Once output is structured, most checklist items become schema `required` fields rather than prose to remember. |
| `error-codes.md` | LangSmith Observability tagging + LangSmith Engine's failure clustering | Instead of grepping a static table, Engine clusters production failures by pattern automatically. |
| `file-naming.md` | Deleted | Deployment's Assistants/thread model gives every run a stable, queryable identity — a filename convention was a workaround for not having a database. |
| `registry-format.md` | The schema for LangGraph Store entries holding derived registry items | See knowledge/registries mapping above. |
| `audit-stages.md` | **The LangGraph graph definition itself** | The single most direct 1:1 port in the repo — every Stage's Purpose/Preconditions/Activities/Decision Logic/Outputs/Transition maps field-for-field onto a node plus its conditional edges. The `CHAIN_INTEGRITY_LOST` chain-verification check at Stage 7 stops being a manually-specified check and becomes a property LangGraph's durable-execution checkpointing already guarantees. |

### assets/ (templates)

| File | Maps to | Reason |
| --- | --- | --- |
| `AUDIT_MANIFEST_template.md` | Deleted as a parsed format — survives only as docstrings on the State schema | Its purpose was teaching a regex parser what to expect; a typed schema needs no intermediary. |
| `PMO_DATA_CHARTER_template.md` | A LangGraph `interrupt()` payload schema, surfaced through Deployment's Studio HIL review UI | The propose → ratify flow is a textbook interrupt: the graph pauses, surfaces the proposed Charter for edit/ratify/decline, and resumes on the human's input. |
| `report_template.html`, `scope_limitation_template.html` | Unchanged — still Jinja2, rendered by a Sandbox tool node |  |
| `logo.jpg` / `logo.png` | Unchanged — korvai.app branding |  |

### Public/

| File | Maps to | Reason |
| --- | --- | --- |
| `IEM-PM-User-Guide.html` | Fleet's in-product guided workflow | The guide's entire reason for existing — no coding, copy-paste prompts per stage — is exactly the gap Fleet closes at the product layer: a PM sees a template and an approval step, never a prompt. |

## Proposed Project Structure

Follows LangGraph's `langgraph.json` + `src/` application-structure convention and Deep Agents' `deepagents.toml` / `AGENTS.md` / `skills/` / `subagents/` project-layout convention, combined for a hosted, multi-tenant product.

```
audit-korvai-app/
├── langgraph.json                # Deployment config — points at the graph below
├── deepagents.toml                # Deep Agents harness config (model, sandbox, skills path)
├── AGENTS.md                      # Always-loaded system prompt — ported from SKILL.md §1, §2, §6
├── mcp.json                       # External connectors (Jira/ADO/Primavera export ingestion)
├── pyproject.toml                 # Orchestration-layer deps only: langgraph, langchain, deepagents
├── .env.example
│
├── src/audit_engine/
│   ├── graph.py                   # The StateGraph — ported from audit-stages.md, one node per Stage
│   ├── state.py                   # Pydantic State schema — ported from findings.schema.json + the 5 Contracts
│   ├── nodes/
│   │   ├── baseline.py            # Stage 0 — Sandbox-executed
│   │   ├── charter.py             # Stage 1 — interrupt() for propose/ratify/edit/decline
│   │   ├── define.py              # Stage 2 — delegates deep-dive to the registry-deriver subagent
│   │   ├── measure.py             # Stage 3 — evidence reading, parallel subagents per artifact
│   │   ├── classify.py            # Stage 4 — invokes the gap-taxonomy skill
│   │   ├── trace.py               # Stage 5 — invokes the root-origins skill
│   │   ├── score.py               # Stage 6 — severity-matrix lookup + interrupt() for Severity 4/5 approval
│   │   ├── synthesize.py          # Stage 7 — structured-output emission (replaces manifest_to_findings.py)
│   │   └── render.py              # Stages 9–10 — Sandbox-executed Jinja2 render
│   ├── tools/
│   │   ├── evidence_reader.py     # column-index-safe tabular reading (Stage 3's real bug fix, ported)
│   │   └── registry_lookup.py     # queries the Store-backed registries
│   └── middleware/
│       ├── evidence_trust_boundary.py   # §6.8 — evidence content is data, never instructions
│       └── read_only_guard.py           # Principle 4 — blocks writes outside the tenant's reports scope
│
├── skills/                        # Deep Agents skills/ — read-only, ported from references/
│   ├── gap-taxonomy/SKILL.md
│   ├── root-origins/SKILL.md
│   ├── scoring/SKILL.md
│   ├── terminology/SKILL.md
│   ├── charter-spec/SKILL.md
│   └── evidence-sufficiency/SKILL.md
│
├── subagents/                     # Deep Agents subagents/ — isolated-context delegation
│   └── registry-deriver/
│       ├── deepagents.toml
│       └── AGENTS.md              # Ported from registry-format.md's derivation procedure
│
├── evals/                         # LangSmith Evaluation datasets
│   ├── gap_classification_dataset.json   # from gap-taxonomy.md's Master Disambiguation table
│   ├── root_origin_dataset.json          # from root-origins.md's Master Disambiguation table
│   ├── pipeline_regression/              # from test_manifest.md, test_findings.json, test_scope_limitation_notice.md
│   └── evaluators/
│       ├── schema_conformance.py
│       ├── terminology_discipline_judge.py   # LLM-as-judge, ported from terminology.md's rule
│       └── no_duplicate_finding.py
│
├── sandboxes/
│   └── evidence-parser.Dockerfile        # pypdf / openpyxl / cryptography — the untrusted-file image
│
├── infra/
│   ├── deployment.yaml            # Multi-tenant Deployment config, autoscaling
│   └── llm_gateway_policy.yaml    # Model routing, spend caps, skill_version pinning
│
├── fleet/
│   └── audit-onboarding-template.json    # No-code template — replaces setup.bat/.sh/.ps1/_gui.pyw
│
└── docs/
    └── (Public/ content — served as Fleet-embedded guidance, not a standalone HTML page)
```

**Note on `knowledge/`:** the literal gitignored folder doesn't carry over as-is — for a hosted, multi-tenant product it becomes per-tenant document storage behind a retrieval tool, indexed at upload time and queried by the Stage 0/2 nodes. The cornerstone rule survives unchanged: no standards on file for a tenant, no audit for that tenant.

## Cross-Cutting Concerns

**Multi-tenant Charter ratification as a durable interrupt.** LangGraph's `interrupt()` plus Deployment's durable execution let a proposed Charter sit paused for days awaiting a PMO lead's ratification without holding compute or losing state — a direct upgrade over the current single-session, in-context propose→ratify flow.

**Sandboxed evidence parsing.** SKILL.md §6.8 discloses an unsolved prompt-injection risk from evidence files. Sandboxes' microVM isolation plus Auth Proxy is the closest thing the ecosystem offers today to an actual technical mitigation — combined with the evidence-trust-boundary middleware, this is defense in depth, not a guaranteed solve; the risk should stay disclosed to users exactly as SKILL.md already does.

**Model/skill provenance via LLM Gateway.** The `skill_version`/`model` fields IEM-PM already hand-parses from a Manifest header become automatic, queryable call metadata. This directly serves a real problem in STATUS.md: two independent PMI audits of the same evidence produced 6 vs. 14 findings, and it was unclear whether that reflected a genuine inconsistency or a model/version difference — Gateway-logged provenance answers that question by default.

**Retiring hand-rolled ops tooling.** `timing_log.py` → Observability; `test_pipeline.py`'s manual assertions → Evaluation's experiment comparison across model/prompt versions; the STATUS.md "Errors Found & Fixed" manual log → Engine's automatic trace clustering and fix-drafting.

**Governance via Context Hub.** As the skill/taxonomy library grows past today's 13 reference files (more per-standard skills at scale, more tenants with their own internal-methodology overrides), Context Hub gives real version control, review, and dev→staging→prod promotion — replacing ad hoc STATUS.md changelog entries with reviewed, environment-scoped skill versions.

## Recommended Build Sequence

1. **Port the 5 Contracts as a typed State schema** (LangGraph) — no agent behavior yet, just the data model. Validate it against the existing `findings.schema.json` and test fixtures before writing a single node.
2. **Port `audit-stages.md` into a graph skeleton** — stub nodes, wire Decision Logic as conditional edges, get the state machine running end-to-end with mocked LLM calls.
3. **Port the judgment stages into Deep Agents nodes/subagents one Stage at a time**, starting with Stage 3 Measure (highest historical bug rate) — validate each against `test_manifest.md` before moving on.
4. **Stand up Observability first** among the LangSmith products — cheapest, most immediate diagnostic value — then Evaluation, using the ported gap-taxonomy/root-origins disambiguation tables as day-one datasets.
5. **Add Sandboxes for evidence parsing once Stage 3 is stable** — a security-hardening pass, deliberately sequenced after correctness, not before.
6. **Wire LLM Gateway** once more than one model/provider is in play, even if only for cost tracking on day one.
7. **Deploy to LangSmith Deployment** behind audit.korvai.app once the full graph passes the ported regression suite.
8. **Turn on Engine** once there's real production traffic to analyze — it needs traces to cluster.
9. **Build the Fleet onboarding template and Context Hub governance last** — adoption and scale concerns, not correctness concerns, and both benefit from a stable graph underneath them.
