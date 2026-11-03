# Next milestone: automatic dataset understanding on AgentCore

User correction and acceptance contract, October 31, 2026.
This supersedes the local-only completion boundary in the previous build report.

## Required experience

The primary workflow is upload + a natural-language business question. Do not
require the user to choose a target, predictor columns, date column, worksheet,
header row, task family or analytical algorithm. Technical schema controls are
not a prerequisite for ordinary analysis.

Automatically inspect the file/workbook before analysis: identify data-bearing
sheets/tables and headers; infer and validate types, identifiers, numeric formats,
dates, missingness, duplicate rows, grain, units and time coverage. Preserve the
source and publish an immutable typed Parquet version plus a saved data profile.
Use deterministic parsing/profiling first and Strands to interpret semantic roles
and resolve the business question into a checked tool plan. Never let a model's
schema guess bypass type, ownership, leakage or data-quality checks.

If competing business meanings cannot be resolved safely, ask a short business
question in the conversation, such as gross versus net sales. Do not send the
user back to a column-mapping form. Explain inferred definitions and limitations
with the result, and preserve corrections as plan revisions.

## Required cloud delivery

Build the application runtime as a reproducible `linux/arm64` Docker image,
store it in ECR and run it in AgentCore Runtime with the required `/ping` and
`/invocations` contract on port 8080. Connect the actual Strands orchestrator,
analyst execution through Code Interpreter and independent reviewer. Existing
standalone/fake-client tests are not the completion criterion.

Persist sources/Parquet/artifacts in S3 and owner-scoped per-job metadata in
transactional cloud storage. Container-local SQLite, process threads and files
must not be treated as cross-session durable cloud state. Use the same image
for local container contract checks and the actual AWS development deployment.
The frontend must invoke that hosted path; a local backend is not the product.

Deploy a separate development runtime in the current AWS account/region first.
Switch the existing public website only after cloud acceptance and a reviewable
integration change. Do not replace the existing runtime or alter unrelated
website work as an incidental deployment step.

## Live acceptance

1. Build/run the ARM64 image and verify its runtime contract.
2. Push the immutable image to ECR and deploy the development AgentCore runtime.
3. Upload CSV and XLSX with differing names/header placement and business columns;
   automatic preparation must produce the same valid canonical tool input.
4. Ask for a monthly revenue chart without any column selection. Verify the
   live AWS calculation and chart against the fixture's expected totals.
5. Ask for a future three-month forecast without technical mapping. Execute it
   in Code Interpreter; preserve imports/versions, exact code, numerical checks,
   review, traces, timing and measured usage.
6. Verify cancellation/cleanup, malformed/ambiguous input, tenant access,
   persisted results after reconnect and a second runtime session.
7. Exercise the frontend against the hosted backend, then record the deployed
   ARN, image digest, artifact lineage and exact verified/unverified boundaries.

## Completion record

The user approved a $10 initial development/test allowance. The separate ARM64
container runtime is now deployed in us-east-1 and passed the chart/forecast
acceptance on real CSV and Excel inputs without technical mapping. S3/DynamoDB
persistence, different runtime-session reconnect, live cleanup/cancellation,
wrong-owner access, idempotency and deletion checks passed. The hosted HTTPS browser now invokes a Cognito-authenticated gateway and AgentCore;
the local IAM bridge is optional. A full 10 MiB staged upload and real user-token
isolation, sign-in/reconnect/logout and chart/forecast flows passed.

See `deployment/2026-10-31-agentcore-dev.json`, `implementation-status.md` and
`validation.md` for evidence. Restricted hosted development login is included; production website cutover
is not included. Four high OS image findings remain a public-release blocker.
The original runtime/public website were preserved.
