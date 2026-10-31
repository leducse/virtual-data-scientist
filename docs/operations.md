# Development operations

The private CloudWatch dashboard is `vds-v2-development` in us-east-1. It uses
service metrics, content-free workflow events and bounded Logs Insights queries.
The `vds-v2-dev-analysis-failures` alarm fires on three failed analysis events in
five minutes. No outbound notification subscription is configured. Operators
need separate AWS IAM permissions; application sign-in grants no telemetry access.

## Signals and their limits

- Completed, failed and cancelled analysis counts come from deduplicated terminal
  stage events. A polling request is not an analysis. CloudWatch delivery itself
  can duplicate events; DynamoDB reservations remain the authoritative ledger.
- End-to-end p50/p95 duration is milliseconds; always inspect sample count. No
  traffic is not proof of health. Per-stage times and quality-gate outcomes are
  queried from logs to avoid a custom metric for every role/dimension combination.
- Measured input/output tokens are grouped by role. Failed model responses can
  have unknown usage. These counters are not an AWS billing statement. Interpreter,
  runtime, gateway, storage, audio and telemetry cost also need reconciliation.
- Active leases and job status live in DynamoDB. A worker lost past its lease
  becomes interrupted when observed; this milestone does not add a scheduled
  orphan-job sweeper, automatic job replay or a guaranteed stale-job alarm.
- Operational logs exclude source rows, filenames, prompts, model/tool content,
  code, credentials and signed URLs. Original evidence remains private and
  owner-authorized. Runtime/framework content logging is disabled. Verify capture
  settings again before enabling additional OTEL auto-instrumentation.

## Response playbook

1. Open the alarm/dashboard and identify the stage, error code and opaque run ID.
   Filter metadata events by run ID to inspect the execution timeline. Check
   service throttling/errors separately from analytical rejections.
2. For numerical/reviewer rejection, keep the result unpublished. Correct the
   recipe/evidence issue and test with synthetic data before rerunning a new job.
3. For a timeout, lost worker or unknown execution outcome, confirm the managed
   Interpreter session is stopped before considering a retry. Never replay a
   possibly completed tool execution automatically.
4. For cleanup failure, inspect the corresponding private run evidence and stop
   only the identified owned sandbox session. Retain unknown usage reservations
   until the outcome and billing exposure are understood.
5. For quota errors, distinguish workspace credits, token reservations, per-minute
   request limits, daily dictation limits and global development admission.
   Verify the ledger; never clear counters merely to make a test pass.

## Current admission policy

Guests have up to five completed analyses. Member development accounts have up
to twenty. One request includes all internal agents, tools and figures. Token
reservations are 50,000 per admitted job, reconciled to measured usage; confirmed
failed/cancelled work releases the analysis credit, while unknown usage retains
a conservative reservation. Viewing lessons/suggestions or changing themes uses
no analysis credit. Member claims preserve up to three guest namespaces and the
existing account namespace without copying source data or trusting client owners.

The deployment has a cumulative twenty-admission development guard. It is not
automatically reset by a browser, account creation, midnight or DynamoDB TTL.
Review/reconcile the $10 authorized allowance before changing that guard. These
application controls are not an AWS-enforced hard spending cap.

Dictation allows at most twenty seconds per request, three issued sessions per
guest/day, ten per member/day, and twenty globally/day. Audio is processed in
memory and is not written to application storage. The initial interaction records
first, then streams Transcribe results after Stop; it is not continuous live voice.
Partial transcripts never submit an analysis. Cancelling a browser connection
does not itself cancel an analysis; use the explicit Cancel job control.

Guest admission and self-signup default off. Public enablement is a release action,
after image findings, quota/security acceptance and operating cost review. Operator
notification channels and additional continuous monitoring are separate choices.

## Rollback

Keep the previous immutable ECR digest and source commit. Change the existing dev
stack's ImageUri/ReleaseId through a reviewed CloudFormation change set; keep the
data/user pools and namespace mapping. Redeploy compatible static/gateway assets
together. Rebuild Lambda ZIPs from pinned manifests if the seven-day deployment
object has expired. Do not delete data or lower/release quota reservations as part
of a code rollback. The original CloudFront URL remains an allowed sign-in origin.
