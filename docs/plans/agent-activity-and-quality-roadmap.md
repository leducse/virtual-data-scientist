# Agent activity and workbench quality roadmap

November 2, 2026. Mode: productionization. The activity viewer is implemented in this change. The ranked backend and product additions below are recommendations, not completed features.

## Activity viewer acceptance

- Keep the small persistent chat status strip and full-name hover/focus labels.
- Map expands inline in the chat. Escape collapses it and restores focus; the rest of the workspace stays usable.
- Adapt the supplied org-tree template: dark surfaces, role-colored card bars, curved parent-to-child arrows, active glow and a traveling dot on a working branch.
- Use the existing React Flow/React stack and persisted event projection. The orchestrator is the parent; tools, numerical checks and saved evidence retain their correct kinds.
- Show only the selected quick/deep route. Before routing, show only the orchestrator. Do not invent completion, percentages, statistics, additional agents or parallel work.
- Only recorded `started` events for an active run animate. Terminal runs stop stale working lights; missing events stay unrecorded. Reduced motion removes moving dots and CSS animation, including when the preference changes while the viewer is open.
- Show recorded durations, attempts and timestamps in cards/details. Selected inspection and expansion survive event updates for the same run; selecting another run resets them.
- Verify desktop, 390px and 320px layouts, event transitions, quick/deep/planning/terminal states, keyboard operation and no browser console errors.

Implementation: `frontend/workflow/view.jsx` and `view.css`; `model.mjs` remains the source of event semantics. Build with `npm run build` in `frontend/workflow`. Generated self-hosted assets are tracked because the deployment publishes them directly. No runtime/model policy changes are required.

Published and verified at the hosted development URL as static release `c753408540858c65cb02`. See [acceptance evidence](../deployment/2026-11-02-agent-org-tree-verification.json). Browser fixtures validate presentation and event transitions; they are not new real-model analysis evidence.

## Ranked BASWE patterns for this workbench

The shared guides overlap. This is a ranking of their applicable patterns, not a proposal to turn every tutorial into another subsystem. The 15-project guide's project numbers are included for traceability. No shared PDF or question-bank content is included in this repository.

| Rank | Guide projects / pattern | Recommendation and measurable completion |
|---|---|---|
| 1 | #1 regression detection, #9 prompt versioning and experiments, #13 evaluation-data generation | Build one versioned evaluation harness. Start with public/sanitized cases across supported ML tasks, ambiguity and known failures. Separate deterministic numerical/security gates from explanation quality. A deliberately bad change must fail named cases; an accepted baseline must pass. Human review is required before feedback becomes a gold case. |
| 2 | #3 failure forensics | Add received/produced/expected evidence and run comparisons to the existing provenance and events. Distinguish an observed failed boundary from an inferred root cause. Sensitive evidence remains private and owner-authorized; operational logs stay content-free. |
| 3 | Calibrated judges and red-team testing (six-project and production guides) | Calibrate the current reviewer using held-out human labels; measure false acceptance/rejection. Add injection, ownership and misleading-data cases to the same harness. Separate roles using one foundation model are not independent model-family agreement. |
| 4 | #2 cost autopilot, #11 gateway | Extend existing quotas/usage with quality, latency and cost per accepted analysis. Try deterministic preparation of approved recipe wrappers before cheaper-model routing; current code asks an LLM to reproduce a wrapper it already constructs. Benchmark numerical parity, actual tokens, p50/p95 and rejection rates. Keep existing auth, policy and unknown-usage reservations. |
| 5 | #15 bounded orchestration; production queues/checkpoints | Add durable dispatch/reconciliation before larger traffic or recurring jobs. Preserve owner/global admission and never blindly replay an unknown interpreter outcome. Fault-inject crashes before/during/after execution; duplicate deliveries must not publish duplicate logical results or consume duplicate admission. |
| 6 | #7 caching | Begin with exact owner/data/plan/recipe/config-version result reuse. Label reused results and preserve original compute/version metadata. Test invalidation, wrong-owner access and false hits. Question similarity alone is not a safe key for numerical answers. Provider prefix caching needs its own measured experiment. |
| 7 | #12 feature flags and gradual rollout | Use small reversible flags for a benchmarked recipe-preparation or model-route change. Record the actual variant in evidence. Broader rollout controls become more valuable with multiple deployments/users. |
| 8 | #4 self-healing documentation | Generate a reviewed capability inventory from supported contracts and evaluation evidence. Propose documentation changes for review rather than silently publishing model-written descriptions of unverified capabilities. |
| 9 | #8 text-to-SQL guardrails | Preserve the existing typed-plan/trusted DuckDB approach. Expand only if arbitrary warehouse questions become a requirement, with read-only access, cost/row/time limits and permission tests. Replacing the current bounded path is unnecessary. |
| 10 | #5 output arbitration | Defer routine multi-model voting. First establish whether a calibrated single reviewer plus numerical checks is insufficient. Consider sampled disagreement experiments; majority agreement is not numerical truth. |
| 11 | #6 hybrid RAG; knowledge-graph RAG in the other guide | Companion-product scope. Useful when users bring definitions, policies and reports alongside tables. Needs document ingestion, page citations, evaluation and authorization before retrieval. No retrieval subsystem is needed just to analyze the currently supported uploaded tables. |
| 12 | #14 multimodal processing | Companion-product scope with document-and-data evidence: preserve tables, units, chart context and page provenance. Evaluate extraction quality independently of the final answer. It is larger than an activity-view improvement. |
| 13 | #10 LoRA/fine-tuning; distillation in the other guide | Defer until reviewed failure data shows a repeatable model limitation that prompts, tools and routing do not solve. Requires a labeled dataset, licensing/data policy and independent quality/cost justification. |

Production-guide retries, permissions and budgets are cross-cutting requirements. Extend the existing controls where evidence identifies gaps; do not replace the stack with every tutorial's framework. Recurring reports come after durable jobs and an explicit source-refresh contract: rerunning an immutable upload does not create fresh data.

## Recommended delivery order

1. Ship and browser-check the activity viewer without changing execution behavior.
2. Establish the quality baseline and reproducible case/variant/rubric contracts.
3. Benchmark deterministic preparation for approved recipes inside AgentCore, preserving actual model fitting, planning, review and numerical checks. Rename any affected activity stage truthfully; do not show a fictional analyst call.
4. Add reviewer calibration and failure/cost comparisons.
5. Add durable job dispatch before growing traffic or scheduling.
6. Add measured caching and selective routing only after the baseline can detect regressions.

## Companion recommendation

**Decision Layer Evidence Studio** is the closest companion: reuse the workbench's provenance, ownership, numerical checks, charts and artifacts to compare workflow variants on approved cases. Its first demonstration should compare current execution against deterministic wrapper preparation, including an intentional regression and a corrected run. It requires new experiment/evaluator contracts; current analysis routes do not automatically become an experiment runner. This remains an unvalidated product hypothesis.

A document-and-data evidence assistant is a second, larger extension. An interview-learning mode can explain original experiments, failures and engineering tradeoffs without reproducing the shared question bank. Neither requires building a separate product in this change.
