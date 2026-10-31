# Implementation status — October 31, 2026

Current development release: `dev-20261031-15`, runtime version 14. Open
https://analyst.decision-layer.com/ with an invited account. Code is pushed to
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
| Plotly and palettes | Three complementary forecast figures; hover, four palettes, exact tables, PNG/HTML/Python downloads and mobile layout verified |
| Learning and suggestions | Reviewed method catalog and profile-driven eligible questions; no technical mapping or automatic paid analysis |
| Agent activity and streaming | Real ordered stage events, active highlights, persisted replay and single-use tickets; native Lambda SSE through CloudFront verified |
| Reproduction | ZIP includes support modules/notebook/SQL/tables; prepared data is an explicit separate export. Downloaded code reproduced exact test MAE in a fresh stopped managed Interpreter |
| Speech | Twenty-second recording limit, real browser AudioWorklet/PCM path with synthetic microphone, Transcribe partial/final text; no automatic analysis submission |
| Trial and login claim | Private AWS test: five analyses succeeded, sixth rejected, account + trial work preserved, member continued, other account denied. Public guest creation/self-signup remain off |
| Operator monitoring | Private CloudWatch dashboard/alarm and content-free stage/usage telemetry deployed; no outbound notification channel |
| Regression/classification | Local fixed recipes and browser proof retained; not enabled in new cloud path |
| Research | Not implemented; required research rejects finalization |
| Hosted login / production cutover | Restricted Cognito development login deployed and tested; owner account provisioned/invitation accepted; first sign-in pending; production website/runtime unchanged |

`docs/deployment/` contains sanitized actual acceptance/scan/cleanup records.
Detailed generated run evidence remains under ignored `data/` and in S3 subject
to development retention. The suite has 71 passing Python tests and twelve passing Node tests. See validation
for exact commands, earlier local proof and unverified boundaries.

## Shortcuts and upgrade conditions

The forecast code policy permits only a reviewed recipe wrapper. Broaden it only
with an expanded capability policy and hostile-code/numerical tests. One bounded
pre-execution code repair is allowed; sandbox execution is never replayed blindly.

Background jobs use SDK async tracking and conditional DynamoDB leases, not a
durable queue. A container interruption becomes an interrupted job after expiry;
add a durable scheduler/reconciliation policy before promising automatic recovery.

The hosted gateway derives ownership from verified Cognito access tokens. Direct
origins and cross-user access were denied in live tests. Production work includes
MFA/revocation/request-rate policy; the optional loopback bridge remains a demo.
Seven-day TTL/lifecycle cleanup is asynchronous; ECR images remain retained.

A full 10 MiB staged upload passed; policy tampering and oversized requests failed.
Published evidence and compact polling are bounded to fit hosted transport.

The final upgraded Amazon Linux image scan reports no critical/high findings and
two medium findings; see `deployment/dev-v2-image-risk-review.md`. Existing
CDK dependency advisories remain separate. The consulting website's earlier auth/503 behavior,
production load, real customer-data accuracy and general cloud ML/research are
not claimed verified.
