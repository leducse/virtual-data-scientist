# Implementation status — November 1, 2026

Current deployment: `dev-20261101-06`, runtime version 22. All six method checks, export reproduction, real browser CSV upload/classification, gallery sign-in, chart interactions and compact monitor checks passed. Open
https://mlworkbench.decision-layer.com/ with a signed-in preview account. Code is pushed to
`feat/product-experience-v2`; the original website/runtime are preserved.

The user corrected the local-only delivery boundary and approved $10 for initial
AWS development/test work. The following reflects actual execution after that
correction. Source plans in `docs/plans/` describe the larger target.

| Capability | Current evidence |
|---|---|
| Upload + question, automatic preparation | Implemented; real CSV and Excel with cover sheet/title row/renamed fields passed without mapping controls |
| Containerized AgentCore deployment | ARM64 nonroot image in ECR; separate `VirtualDataScientistV2Dev` stack UPDATE_COMPLETE; manifest records immutable digest/release |
| Strands planner | Live Nova Pro inferred task, exact date/measure and follow-up forecast horizon |
| Monthly chart | Live hosted DuckDB: 36 months, source total 579,060; trusted checks passed |
| Forecast | Live analyst → Code Interpreter → trusted numerical checks → independent reviewer accepted; baseline plus two candidates |
| S3/DynamoDB persistence | Sources/Parquet/audits/results and conditional per-job state; new runtime-session reconnect passed |
| Cancellation and cleanup | Application terminal-state/no-late-result check; direct live sandbox cancel and normal sessions confirmed TERMINATED |
| Ownership/idempotency/deletion | Live wrong-owner reads/deletes denied, key conflict rejected, deleted run inaccessible and S3 prefix empty |
| Frontend and verified-user gateway | Hosted CloudFront/Cognito/Lambda path passed Excel upload/chart/forecast/reload/download/logout; optional local bridge retained |
| Plotly, React Flow and palettes | Three complementary forecast figures; hover, four palettes, exact tables, PNG/SVG/HTML/JavaScript/Python downloads, and mobile layout verified |
| Chat and login continuity | Left conversation / right selected evidence; actual Back, question/file preservation, one automatic job after sign-in, reload without repeat submission, and logout revocation verified |
| Learning and suggestions | Reviewed method catalog and profile-driven eligible questions; no technical mapping or automatic paid analysis |
| Agent activity and streaming | A 42px chat status strip uses actual working points and hover details; Map opens the parent–child viewer with keyboard/modal/mobile checks. Persisted replay and authenticated SSE remain verified |
| Reproduction | ZIP includes support modules/notebook/SQL/tables; prepared data is an explicit separate export. Downloaded code reproduced exact test MAE in a fresh stopped managed Interpreter |
| Speech | Twenty-second recording limit, real browser AudioWorklet/PCM path with synthetic microphone, Transcribe partial/final text; no automatic analysis submission |
| Trial and login claim | Private AWS test: five analyses succeeded, sixth rejected, account + trial work preserved, member continued, other account denied. Public guests remain off; self-service signed-in preview is enabled with a persistent 100k-token / twenty-analysis account limit |
| Operator monitoring | Private CloudWatch dashboard/alarm and content-free stage/usage telemetry deployed; no outbound notification channel |
| Regression/classification | Live AgentCore execution, source/split/baseline/metric checks, independent model acceptance and downloaded Python reproduction passed |
| Clustering/PCA/anomalies | Live sealed AgentCore recipes passed source checks, independent model review and downloaded Python reproduction; three diagnostics per task |
| Teaching gallery | Eight immutable attributed snapshots and two bounded reviewed OpenML ID/version imports; profiling uses normal owner-scoped ingestion without a model analysis |
| Research | Not implemented; required research rejects finalization |
| Hosted login / production cutover | Restricted Cognito development login deployed and tested; owner account provisioned/invitation accepted; first sign-in pending; production website/runtime unchanged |

[Current showcase verification](deployment/2026-11-01-ml-showcase-verification.json) links method-specific live runs, browser metrics and cleanup. All temporary test datasets/accounts were removed; Interpreter sessions were confirmed terminated. The cumulative development ledger is 33/36 and was not reset.

[Latest status-bar verification](deployment/2026-11-01-chat-statusbar-verification.json) and [input/model audit](audits/2026-11-01-analysis-authenticity.md) add a real Wine upload, primary-source comparison, reproduction and local negative control.

`docs/deployment/` contains sanitized actual acceptance/scan/cleanup records.
Detailed generated run evidence remains under ignored `data/` and in S3 subject
to development retention. The suite has 97 passing Python tests and 30 passing Node tests. See validation
for exact commands, earlier local proof and unverified boundaries.

## Shortcuts and upgrade conditions

The forecast code policy permits only a reviewed recipe wrapper. Broaden it only
with an expanded capability policy and hostile-code/numerical tests. One bounded
pre-execution code repair is allowed; sandbox execution is never replayed blindly.

Background jobs use SDK async tracking and conditional DynamoDB leases, not a
durable queue. A container interruption becomes an interrupted job after expiry;
add a durable scheduler/reconciliation policy before promising automatic recovery.

The hosted gateway bootstraps ownership from verified Cognito access tokens and
issues a server-stored opaque HttpOnly session, bounded to the verified expiry. Direct
origins and cross-user access were denied in live tests. Production work includes
MFA/revocation/request-rate policy; the optional loopback bridge remains a demo.
Seven-day TTL/lifecycle cleanup is asynchronous; ECR images remain retained.

A full 10 MiB staged upload passed; policy tampering and oversized requests failed.
Published evidence and compact polling are bounded to fit hosted transport.

The final upgraded Amazon Linux image scan reports no critical/high findings and
two medium findings; see `deployment/dev-v2-image-risk-review.md`. Existing
CDK dependency advisories remain separate. The consulting website's earlier auth/503 behavior,
production load, real customer-data accuracy and external research are
not claimed verified.

React Flow replaces the D3 activity map in the latest frontend. Real hosted
forecast stage highlights, animated handoffs, node inspection, state preservation,
responsive layout, resize fitting, cleanup and unchanged analytical charts passed.
See `deployment/react-flow-hosted-acceptance.json` and `plans/react-flow-activity.md`.

The latest activity map uses an orchestrator parent with outward child arrows;
execution order is retained in the timeline. The root's whole-job status and
planning status are distinguished. This is a frontend correction verified with
recorded traces, not new selective agent-routing capability.
