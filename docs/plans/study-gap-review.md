# Virtual Data Scientist: review against the Google study materials

Reviewed October 31, 2026. Scope: compare the proposed application design with Scott's Google systems-design study materials. This is a design review and plan update; no application code, Drive documents, or cloud resources were changed.

## Main finding

The plan already addresses the main execution architecture: Strands task routing, a deterministic quick path, bounded Python analysis, independent numerical checks, a reviewer, optional cited research, versioned Parquet, ownership checks, durable job records, and tracing. The strongest remaining improvements concern business meaning, capacity control, failure recovery, privacy over the data lifecycle, release discipline, and learning from user corrections.

These additions fit the four existing agent roles. They primarily belong in application services, schemas, tests, and operating procedures.

## Materials used

- [GenAI Systems Design Interview Cheat Sheet](https://docs.google.com/document/d/1_e4C5XKGPJmxBS-Ne9Sg2tGwghm4SxgSK3HLFnWURYU/edit?usp=drivesdk): outcome and constraints; authorization; duplicate prevention; freshness; capacity; evaluation and release.
- [Google FDE — Agentic Requirements and AI-DLC Interview Guide](https://docs.google.com/document/d/1Y3rVujPBFqPH0GmSfY5rRT60eWLZT2fEdi-4caL-pIE/edit?usp=drivesdk): sections 1–5 and Operations, especially metric definitions, node contracts, acceptance criteria, feedback, and operating ownership.
- [AI Engineering Interview Flashcards — Concise Answers](https://docs.google.com/document/d/1LIZX_ePD8YBVzYwM5CBVRXeVL0MqQpa2cZU8wrINgiE/edit?usp=drivesdk): questions 24, 29, 31–35, 40, 42–60, 63, 67, 73, 82, and 89–90.
- [GenAI Systems Design Learning Notebook](https://drive.google.com/file/d/1y-8EsdGeZ12hHdApG0NZKpjcWpXRsSjG/view?usp=drivesdk): the current Drive copy contains 61 cells. Read its relevant explanatory cells, including the added corrections about budgets versus circuit breakers, structured state, safe retries, and authorization. Notebook code was not executed.
- [Google reading pack](https://drive.google.com/file/d/1Uq9_o-68zkxSiRC0czYndToHNdhjVeF4/view?usp=drivesdk): R1–R3, W1, and the delivery worksheet. Its coaching recommendations are distinguished from published source claims.

The folder's start document identifies the notebook as the longer reference and the cheat sheet as the quick review. The architecture document's text extraction exposed mainly diagram headings, so this review does not claim to have inspected its diagrams. The study package itself distinguishes practice synthesis and community material from official Google requirements.

## Prioritized gaps and acceptance criteria

### 1. Business definitions before analytical method selection

**Coverage before review: partial.** The plan validates schema, targets, and method eligibility, but has no explicit contract for what a business measure means. Recording column types alone cannot resolve gross versus net revenue, dollars versus thousands of dollars, monthly versus annual churn, or the cost of a false positive.

**Add:** a versioned analytical brief attached to the dataset and run. Include the metric definition, row/entity grain, units/currency, timezone/calendar, relevant exclusions, target, horizon, scoring objective, and important assumptions. Distinguish confirmed facts from inferred assumptions. Ask a focused clarification only when the ambiguity could materially change the answer. For classification, choose metrics and thresholds based on class balance and decision costs, using validation data rather than the final holdout.

**Acceptance:** fixtures with ambiguous revenue definitions and scale factors request clarification or clearly state a defensible assumption; confirmed definitions persist into follow-up questions; all chart and narrative values use the same definition. A highly imbalanced classifier cannot be accepted solely because overall accuracy is high.

**Source:** agentic guide sections 1, 3, and 4; flashcards 3, 82, and 89–90.

### 2. Capacity and spending controls before expensive work starts

**Coverage before review: partial.** There are time, candidate, and correction limits, but no complete policy for shared model quotas, simultaneous runs, per-user spending, or traffic spikes. Measuring cost after a run does not prevent an expensive run from starting.

**Add:** per-user and global request, token, concurrency, and spending limits, enforced by application code before calls. Reserve an estimated upper bound for the next operation, including output tokens, then reconcile recorded usage. Separate quick-query capacity from deep and research work. Detect repeated tool calls with the same normalized arguments and no new evidence. Bound pending-job count and maximum waiting time. If durable queuing is not yet implemented, reject excess work clearly rather than acknowledging a job the system cannot reliably retain.

**Acceptance:** one user's burst cannot consume all interactive capacity; the next model/tool call is denied when its reservation exceeds the remaining budget; queue age and rejection are visible; a controlled burst test measures quick-path latency while deep work is active. Configure actual thresholds from the agreed workload and benchmark, rather than inventing a production capacity promise.

**Source:** cheat sheet Scale and Spend; flashcards 24, 33, 35, 55–56, and 73; notebook cells 40, 42, 56, and 59.

### 3. Explicit failure behavior and uncertain operation outcomes

**Coverage before review: partial.** Idempotency, checkpoints, cancellation, and retry are already planned. The missing detail is which failures may be retried and what happens when a remote operation might still be running.

**Add:** typed errors; per-call timeouts and an overall deadline; bounded exponential backoff with jitter for safe transient errors; no retry for invalid input or denied access; a circuit breaker around a persistently failing dependency. A fallback must have passed the relevant evaluation cases and preserve the same data and permission boundaries. Return checked partial results with a clear status when full completion is unavailable.

Persist external session/command identifiers where available. If a start or execute request loses its response, record an uncertain outcome, query authoritative status when supported, and reconcile before repeating expensive execution. Where the external API offers neither deduplication nor reliable status lookup, do not claim exactly-once execution; contain the ambiguity and use a controlled retry procedure. Conditional job claims and revision checks must also prevent an old worker from publishing over a newer result.

**Acceptance:** fault injection covers rate limiting, timeouts, denied access, a lost response after execution begins, a worker restart, and a delayed result from an obsolete run. Retries stay bounded and uncertain operations are not silently duplicated.

**Source:** cheat sheet Recover Without Duplicates; flashcards 31, 34, and 55; notebook cells 17, 26, and 40. The notebook explicitly corrects its simplified example: an iteration or token cap is a run budget; a circuit breaker stops calls to an unhealthy dependency.

### 4. Privacy, retention, and deletion across derived data

**Coverage before review: partial.** Owner checks, private storage, minimized web queries, and safe tracing are planned. Retention periods, source deletion propagation, and permitted processing locations are not defined.

**Add:** a lifecycle inventory covering original uploads, Parquet, profiles, code, predictions, charts, research records, caches, traces, evaluation samples, and backups. Assign retention and deletion behavior to each. Record sensitive-field handling and approved data/model processing locations. Deletion must make new application reads unavailable immediately and propagate to derived records; document the expiry window for previously issued download links and any backup/log retention exceptions. Versioned object storage requires a version-aware purge policy. Restoration must not silently resurrect deleted user data.

**Acceptance:** delete a test dataset and verify its lineage-linked artifacts and caches become inaccessible and then expire or purge according to the declared policy. Verify redaction on logs, errors, and model context. Do not copy raw customer data into permanent evaluation fixtures by default. Test the configured model route and storage/log destinations against the selected regional policy.

**Source:** cheat sheet Authorize and Control and Storage/Compute; flashcards 15, 63, 67, 77–80; notebook cells 43 and 56. This is a proposed product policy, not a claim that a particular legal regime applies.

### 5. Calibrated review and controlled releases

**Coverage before review: partial.** Golden examples, deterministic checks, and managed evaluation are planned, but passing thresholds, judge calibration, and a rollback procedure are not explicit.

**Add:** a versioned evaluation set with expected properties, human-reviewed labels, ambiguous/no-answer cases, and difficult cohorts. Measure the reviewer's false acceptance and false rejection rates using deliberately wrong numerical claims, unsupported citations, and valid outputs. Do not tune on the final held-out release set. Require quality, authorization, latency, and cost thresholds before changing prompts, model configurations, method policies, or tool schemas.

Package those components into a release manifest. Keep each running job on one manifest; introduce changes behind feature flags, use shadow or limited pilot traffic as appropriate, and preserve a known-good rollback. Shadow tests must not repeat external side effects and must fit an explicit budget. Provide an operator control to stop new deep/research work while keeping valid existing artifacts readable. Identify an operating owner, alert thresholds, and a short recovery runbook.

**Acceptance:** a deliberately regressed prompt or model fails the release gate; switching back restores the prior configuration; the run's evidence identifies the exact manifest; an interrupted deployment cannot mix incompatible stage versions.

**Source:** cheat sheet Evaluate and Ship; agentic guide section 5 and Operations; flashcards 42, 44, 46–49, and 53–59; notebook cell 48.

### 6. Bounded conversation context and mid-run corrections

**Coverage before review: partial.** Sessions, cancellation, and durable runs are covered. The design does not yet specify which conversational facts must survive compaction or how a changed question affects an in-flight plan.

**Add:** store the active dataset/version, analytical brief, user corrections, selected target, plan revision, and artifact IDs as structured state. Send each role only the evidence it needs, with token and tool-result size limits. Use conversational summaries for convenience, with references back to authoritative records. A correction creates a new plan revision: stop obsolete work at a safe boundary, invalidate its dependent results, and reuse unchanged ingestion and profiling outputs.

**Acceptance:** after a long conversation, “use net revenue instead” updates the correct metric without switching datasets or accepting an old worker's result. Reconnection preserves the current plan and progress. Large logs or source documents do not overwhelm the next model call.

**Source:** flashcards 20, 29, and 40; notebook cells 6, 33, and 56; agentic guide section 3.

### 7. Feedback and a measurable definition of success

**Coverage before review: largely missing.** The plan measures performance and cost per successful task, but does not yet define success from the user's perspective or capture corrections in a repeatable improvement process.

**Add:** a lightweight correction/report control linked to the run ID and release manifest, plus measures for time to a verified useful result, completion, abandonment/rephrasing, and rework. Define separate success criteria for charts, ML analyses, and research. Include retries, unsuccessful runs, research, execution, storage, and observation costs in the cost-per-success calculation. Review feedback before converting it into a sanitized regression case; avoid automatic behavioral changes from a single rating.

**Acceptance:** a user reports a wrong aggregation, the report points to the exact calculation and configuration, and a verified correction becomes a regression case. The dashboard separates technical job completion from useful task completion.

**Source:** agentic guide sections 1, 4, and 5; flashcards 43, 47, 58–59; notebook cells 47 and 59.

## Scope and implementation order

Integrate the analytical brief, structured context, and budget/error contracts into the early schema and service work. Validate capacity, safe retries, and uncertain-operation handling with the first execution spike. Add deletion behavior while implementing ingestion and ownership. Build reviewer calibration and release gates with deep analysis. Finish feedback, operating ownership, and rollback rehearsal before the public cutover.

Retain the existing choices that the materials support: deterministic calculations for exact metrics; a small curated tool set; independent verification; a quick path that avoids unnecessary model calls; and explicit dependencies before parallel work. Compare the planned workflow against a simpler baseline in evaluations to establish whether extra model calls improve outcomes enough to justify their cost.

Do not add a vector database, GraphRAG, a feature store, autonomous retraining, GPU serving, or extra agent roles merely because the study material covers them. Reassess those features when a concrete requirement and a measured benefit justify them. For the initial portfolio release, an explicitly interrupted job with a safe retry can be acceptable; claiming automatic durable recovery requires a stronger queue/workflow implementation and recovery tests.

## Primary-source cross-check

The reading pack's [Google Research article on scaling agent systems](https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/) supports testing architecture choices against task structure; its results are benchmark findings, not a guarantee for this application. Google's [multi-tenant agentic architecture guidance](https://docs.cloud.google.com/architecture/multi-tenant-agentic-ai-system) also discusses model-capacity limits, transient-error handling, context limits, and tenant quota enforcement. The recommendation here applies those principles to the existing AWS design without copying Google's full platform topology.

The official [Professional Agentic Architect guide](https://services.google.com/fh/files/misc/professional_agentic_architect_exam_guide_english.pdf), sections 4–5, covers evaluation, operations, and secure execution. The [Professional ML Engineer guide](https://services.google.com/fh/files/misc/professional_machine_learning_engineer_exam_guide_english_new.pdf), sections 2–4, reinforces privacy, experiment lineage, model choice, and controlled model rollout. These are coverage outlines, not an implementation checklist requiring every named service.

## Validation boundary

Read the live Drive materials, downloaded and parsed the notebook without executing its code, checked relevant primary references, and compared them with the complete saved implementation plan. The source text supports the principles above; the application-specific acceptance criteria are recommendations from this review. No new code or cloud integration was exercised.
