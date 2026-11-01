# Validation record

## ML showcase iteration — current validation

- 96 Python and 27 JavaScript tests pass. The eight ML showcase tests execute all six dataset/task combinations, every exported Python script and notebook code cell. A 20,000-row binary classification case with long labels stays within the sandbox transport bound.
- Source-based numerical checks reject altered labels, projections, metrics and candidate evidence. Sealed code wrappers reject plan/result mutation. Reviewer metrics and unsupported prose numbers remain publication gates.
- Missing/mixed Penguins features, target exclusion, curated snapshot hashes and reviewed OpenML metadata changes are covered. Production workflow/streaming dependency audits report zero advisories.
- Local mobile checks measured a 137px sticky monitor at 390px viewport width, with finite parent-child arrows and no horizontal overflow. Hosted checks are recorded separately.
- Current runtime image ECR scan: zero critical/high and two medium OS findings; see `deployment/dev-20261101-05-image-scan.json`. This is not a comprehensive dependency/security assessment.


- Live AgentCore classification, regression, clustering, PCA, anomaly detection and forecast passed numerical/model review and downloaded-script reproduction. Final release05 additionally passed a real browser CSV upload/classification without column controls; full script and all notebook cells reproduced in Python 3.12.13 with pinned libraries.
- Gallery browse/sign-in/profile handoff did not start an analysis. Both reviewed OpenML imports passed on AWS; an unreviewed URL was rejected. Exactly one explicit browser analysis was added; Back/reload retained the session and did not resubmit. Logout survived reload.
- Browser Plotly 4.2.0 rendered three figures under the self-only script policy, without console errors. Hover/palette changes, all figure formats, full analysis/prepared-data downloads, offline HTML with no external requests, keyboard inspection and Expand passed. Monitor height 137px on desktop and 390px mobile; sticky top zero, six finite nodes/arrows, no horizontal overflow.
- Acceptance found and corrected a reviewer preview-cap mismatch and materially different continuous Holt optimizer fits across numerical versions. The revised training-only twelve-setting grid matches across versions with strict prediction gates unchanged. Three failed admissions remain counted; ledger 30/36. All temporary data/users were removed and managed sessions terminated.
- [Current evidence](deployment/2026-11-01-ml-showcase-verification.json), [forecast library parity](deployment/2026-11-01-forecast-library-parity.json), [final image scan](deployment/dev-20261101-05-image-scan.json). Existing voice/CloudWatch proofs below remain historical; this iteration did not re-test transcription or production load.

## Earlier parent–child orchestration map

- 25 JavaScript tests pass, including parent ownership, active-child arrows,
  coordinator lifecycle, phase/job durations, terminal behavior and outer paths.
- Recorded forecast replay verified every edge starts at the orchestrator,
  no edges cross another child's card, and zoom/selection survive event updates.
  Wide/mobile fit, repeated viewport changes and terminal highlighting passed.
- Controlled node measurements are now retained; responsive fitting waits for
  measured dimensions rather than assuming the canvas is initialized.
- This correction introduces no model execution, Interpreter session or backend
  routing changes. The earlier live runtime proofs below remain separate.
- Current quick and forecast paths were verified in `cloud_service.py` and
  `agent_workflow.py`; general analyst-only/code-only routing is not yet present.



## Earlier React Flow viewer

- 79 Python tests and 23 Node tests pass. The frontend build and full dependency
  audit pass; CI rebuilds the self-hosted JS/CSS/licenses for reproducibility.
- Local replay uses `tests/fixtures/workflow-forecast.json`, a sanitized earlier
  hosted forecast. It is explicitly a replay, separate from the new live check.
- Live hosted forecast `f44d676dda903049d74dd76ca53d1f01` succeeded in unchanged
  backend release 17. Working orchestrator/analyst/Interpreter/reviewer and active
  handoffs were observed through actual persisted SSE events. Six graph nodes
  completed and three analytical charts rendered. Independent review accepted;
  MAE 304.17112299465106; Interpreter TERMINATED; measured model tokens 4,568.
- Node inspection, keyboard activation, zoom, same-canvas/viewport/selection
  preservation, reduced motion, repeated larger/compact fitting, mobile, reload
  and disposal on dataset deletion passed. There was no horizontal overflow at
  390px. Synthetic data/results and temporary users were removed.
- Global admissions were 18/20 at this check and were never reset. No runtime,
  Cognito or infrastructure deployment was needed; only static assets changed.
- [Hosted evidence](deployment/react-flow-hosted-acceptance.json),
  [canvas screenshot](agent-flow-react-flow.png),
  [plan/source boundaries](plans/react-flow-activity.md).



## Earlier chat / preview releases 16–17

- 79 Python tests and 17 Node tests; source compilation, JS syntax, pip check and
  whitespace checks passed. Prior release results below are historical.
- Real hosted Back → restored question/file/enabled controls; Cognito Sign up
  form present; successful sign-in automatically sent one saved request.
- Summary `8440f2066f933e281f301c5c5f05f12a` and follow-up forecast
  `21c401435039d47e83a086bf4e93726d` succeeded in AgentCore release 16. Exactly
  two runs survived reload. Interpreter status was TERMINATED; independent
  review accepted. Total measured input/output usage: 6,745 tokens.
- Three ECharts figures: two linked time views and an isolated categorical MAE
  comparison. Four palettes and D3 activity map verified; 390px viewport has no
  horizontal overflow. PNG dimensions/signature and pinned JavaScript export
  checked; self-contained HTML opened and rendered from a local file.
- Account-limit blocking was tested with an explicitly set synthetic acceptance
  account fixture at 100,000 tokens (not by spending that amount). API returned
  429 quota_exceeded, Send was disabled, and charts/downloads remained available.
  The fixture was restored to actual measured usage. Global admissions stayed
  14/20; this ledger was never reset.
- Opaque login cookie/reload and draft persistence were verified in the browser.
  Logout cleared the draft and a replay of the old HttpOnly cookie returned 401.
  New code tests cover expiry/revocation, strict Origin, account isolation,
  invalid-JWT fallback rejection, wrong callback state, BFCache controls and
  identity-bound pending intent.
- Source asset releases are immutable/content-addressed. A stale HTML/new script
  mismatch observed during an in-progress publish was repaired and the final
  coherent hosted release was rechecked.
- Final release 17 / runtime version 16 smoke: exact total 579,060; 2,008
  measured model tokens; repeated submission returned the same job; zero residual
  token reservation. Synthetic data/results were deleted. Global admissions
  advanced once to 15/20. [Runtime evidence](deployment/dev-v3-final-runtime-check.json).
- Current ECR scan: zero critical/high and two medium findings (same reviewed
  base image). ECharts/D3 dependency graph npm audit: zero reported vulnerabilities.
- [Consolidated verification](deployment/dev-v3-chat-verification.json).
- [Actual cloud acceptance](deployment/2026-10-31-chat-hosted-acceptance.json),
  [web manifest](deployment/dev-20261031-16.json),
  [final runtime manifest](deployment/dev-20261031-17.json),
  [library research](research/visualization-engine.md).



## Product experience v2 — release dev-20261031-15

The branded development app is https://analyst.decision-layer.com/; runtime
version 14 is READY and both stacks are UPDATE_COMPLETE. Final runtime health
confirmed release dev-20261031-15. The browser exercised real analysis releases
12/13; release 14 additionally fixes conservative handling of unknown execution
reservations, covered by a dedicated regression case.

- 71 Python tests and 12 Node tests passed, with source compilation, JS syntax,
  dependency checks and whitespace checks. GitHub Actions also validates the branch.
- Native browser Cognito login, automatically profiled Excel cover sheet/header
  row three, 72 rows and USD, two eligible suggestions and zero mapping selectors.
- A suggested question exposed an inconsistent model task/tier pair. Tier is now
  derived deterministically from task; the same suggested question then passed.
- Live forecast: three Plotly figures separating history, untouched test and
  validation comparison; real tooltips; ocean palette preserved across reload and
  exported figures. Six methodology lessons were available.
- Real active-agent highlight observed. The private AWS transport probe received
  an initial SSE event before a later state update; consumed tickets were rejected.
  Polling remains a fallback; no stream request starts or replays analysis.
- PNG, self-contained HTML, Python and code/notebook ZIP downloaded. A separate
  prepared-Parquet download matched the saved checksum. Exported Python executed
  in a new managed Interpreter, reproduced linear_trend and test MAE
  304.17112299465106 on Python 3.12.13; the session was confirmed TERMINATED.
- Synthetic microphone audio passed through the actual browser recording,
  AudioWorklet/downsampling and native Transcribe proxy. Expected and observed:
  “Show monthly revenue for the last year.” The editable transcript did not
  create an analysis. Physical microphone hardware was not tested.
- Private IAM-only guest acceptance: five completed summaries, sixth request 429,
  verified login claim preserving both namespaces, member continuation and
  cross-account denial. Synthetic accounts/function/data were removed; admission
  accounting was retained. Public guest creation/self-signup stay disabled.
- Desktop 1440 and mobile 390 pixels had no horizontal overflow. Screenshots were
  inspected. App console: zero errors/warnings. Reload restored three saved run
  records and the palette; logout hid the workspace.
- Workflow/model-usage records were observed in CloudWatch. Known synthetic
  source/filename and signed-URL markers had zero matches in recent runtime logs.
  This is a scoped marker check, not a universal secret audit. Alarm notifications
  were not sent or configured.
- Final ECR basic scan: zero critical/high, two medium. The Amazon Linux base
  replaced the previous Debian findings; see the dedicated image risk review.

Evidence: [final verification](deployment/dev-v2-verification.json),
[private trial](deployment/dev-v2-trial-acceptance.json),
[export reproduction](deployment/dev-v2-export-reproduction.json),
[telemetry check](deployment/dev-v2-telemetry-check.json),
[current image review](deployment/dev-v2-image-risk-review.md).
Screenshots: [three-figure result](workspace-v2-results.png),
[mobile](workspace-v2-mobile.png).

Current billed project spend is not fully reconciled. Public cost/abuse controls,
notification delivery, continuous voice, durable job recovery and broader cloud
ML/research remain outside this verified development release.

## Earlier hosted acceptance — release dev-20261031-08

The separate HTTPS workspace is live at
https://d19bkp3wlr8r7k.cloudfront.net/. Both development stacks are UPDATE_COMPLETE;
AgentCore reports READY, runtime version seven, release dev-20261031-08.
[Hosted resources](deployment/2026-10-31-hosted-web.json),
[actual acceptance](deployment/2026-10-31-hosted-acceptance.json) and
[final configuration checks](deployment/2026-10-31-hosted-verification.json)
record the proof. The existing consulting website and original runtime remain
unchanged; this is a restricted development deployment.

- 58 Python tests passed in 6.288 seconds. Four Node auth tests passed. Source
  compile checks, both browser script syntax checks, pip check and diff whitespace
  checks passed. Source compilation excludes vendor/CDK template files.
- Actual Cognito authorization-code/S256-PKCE sign-in completed in the browser.
  Reload returned to the gate; provider-session sign-in restored the dataset,
  question and results. Logout hid the workspace. Access tokens were held only
  in memory; no password/token was written to a file or printed.
- Two administrator-created temporary users received no invitations and were
  removed after the checks. Anonymous/invalid/ID-token access returned 401;
  direct Lambda and static-bucket requests returned 403. Owner spoofing was
  ignored, wrong-owner staging/result access returned 404, and altered upload
  policy keys returned 403.
- The exact 10 MiB boundary was uploaded straight to S3, automatically prepared
  and deleted through the authenticated API. An oversized initialization failed
  with 413. Actual S3 CORS allows only the development HTTPS origin.
- The real hosted browser uploaded a different Excel fixture with a cover sheet,
  title row, When Sold/Net Sales/Business Unit and dollar-formatted values.
  Automatic preparation selected Transactions/header row two, typed dates/numbers
  and inferred USD. No technical mapping controls were used.
- Chart run `49f3500fa976bef955033a623ce0335a`: 36 months, total 579,060,
  numerical review passed, end-to-end 2,744.57 ms.
- Forecast run `24aba75962a2dfb446257277ebf61f5f`: real Code Interpreter,
  chronological selection/test, trusted checks and separate reviewer acceptance.
  End-to-end 14,047.49 ms; recipe analysis 2,326.09 ms; test MAE
  304.17112299465106 USD versus naive 860.0. Measured model usage: 3,984 input /
  915 output tokens. This tiny synthetic fixture is not a general accuracy/SLO
  or statistical-significance claim.
- Session `01M69GGEHGSK5C0VQTMEH4GE3W` was queried and confirmed TERMINATED.
  Full evidence download `analysis-24aba759.json` completed after reconnect.
- Desktop 1440 px and mobile 390 px: no horizontal overflow or mapping selectors;
  upload/question fields labeled; screenshots visually inspected. Final app
  navigation had zero console errors/warnings. Cognito's own login page had an
  unrelated favicon.ico 404 during the initial redirect.

Screenshots: [hosted desktop](workspace-hosted.png),
[hosted mobile](workspace-hosted-mobile.png). The model review's raw prose can
contain weak or misleading limitations. Its disposition and metric consistency
are gated; primary UI text uses the checked facts/disposition. Raw review remains
in the evidence and expander rather than being presented as validated narrative.

Polling now budgets included result bodies to 2 MiB, defers older bodies to
individual retrieval and always fetches full evidence for download. Each
published artifact is bounded to 2 MiB. Unit coverage verifies compact-history
bounds while full evidence remains available.

Deployment failures were diagnosed before declaring success: account Lambda
quota rejected a reserved allocation; the empty retained bucket/pool were
imported into the corrected stack without duplicates. An incorrect managed
cache-policy ID was replaced using the live AWS policy listing. CloudFormation
caught an S3 CORS property-name error before execution; the corrected change set
passed and deployed. No other account quota or production resource was changed.

The base image is pinned and locale constrained. The
[actual v8 scan](deployment/2026-10-31-image-scan-v8.json) still reports four high,
nine medium and three low OS findings. See the
[primary-source risk review](deployment/2026-10-31-image-risk-review.md).
Public production release remains blocked pending fixes or explicit risk review.
MFA/revocation/request-rate policy, durable artifact retention, broader cloud
recipes/research, production load and reconciled AWS billing remain unverified.
The live test accounts were removed. The actual owner account is now provisioned
and Cognito accepted its email invitation; inbox delivery and the first sign-in
remain unconfirmed. No temporary password was retrieved or saved locally.


October 31, 2026. Current scope: separate AWS AgentCore development deployment
with automatic preparation and live analytical acceptance. The public website
was not switched. This record separates actual cloud proof from local/mocked
checks and older history.

## Prior runtime checks (before hosted sign-in)

| Check | Observed result |
|---|---|
| `.venv/bin/python -m unittest discover -s tests -v` | 50 passed in 5.766 seconds |
| Python compileall for analysis_engine/scripts/model_registry/CloudDataScientist | Passed |
| `node --check static/workspace.js` | Passed; native client has no separate frontend package build |
| `.venv/bin/python -m pip check` | No broken requirements |
| `git diff --check` | Passed |
| ARM64 Docker contract | `/ping` and health invocation passed; nonroot UID 10001; package check passed |
| CloudFormation | `VirtualDataScientistV2Dev`: UPDATE_COMPLETE; separate runtime, private S3, DDB, ECR and scoped role |
| ECR image scan | COMPLETE: 4 high, 9 medium, 3 low OS findings; no critical reported; public-release blocker |
| Existing backend/AgentCore CDK builds | Earlier TypeScript checks passed; AgentCore Jest one passed; those trees are not used by the new deployment |

The suite covers automatic table/header/date/currency/identifier handling,
ambiguous/formula/size failures, aggregation grain, chronological forecast
cutoffs/refits, false metric/future-information rejection, training-only local
supervised preprocessing, owner/state/idempotency/delete behavior, cancelled
terminal runs, SDK lifecycle/output/deadline/unknown-outcome contracts, approved
code capabilities, bounded repair and numeric narrative gates. AWS state tests
use Moto; workflow tests use fake model/interpreter clients. Live proof follows.

## Prior direct-runtime analytical acceptance

Runtime/model/image/account are recorded in
[the deployment manifest](deployment/2026-10-31-agentcore-dev.json).
[Final runtime verification](deployment/2026-10-31-runtime-verification.json)
confirms READY/version five, the exact digest/release, a successful health call,
no active global leases and the browser forecast sandbox TERMINATED.
[Sanitized live results](deployment/2026-10-31-live-acceptance.json) preserve
actual plans, versions, metrics, timings and per-role usage.

- CSV: 72 source rows, 36 months, total 579,060. The live planner selected date
  and revenue. Forecast run `ff569340b53b397185a4c8be468bce40` succeeded in
  15,201.61 ms end to end on release dev-20261031-04.
- Excel on final release dev-20261031-05: cover sheet ignored; Transactions,
  header row two, When Sold and Net Sales selected automatically. Quick run
  `ca241719ffd3ba17bfe691900d2bd700` succeeded in 3,143.71 ms. Forecast
  `c17b9ead260fe1b1f30ed4d72e77dad9` succeeded in 13,264.04 ms; sandbox work
  4,010.63 ms, recipe analysis 1,704.15 ms.
- Both forecasts selected linear trend using chronological validation; final
  test MAE 304.17112299465833 versus naive 860.0. Jan–Mar 2026 predictions:
  22,723.428571 / 23,082.262548 / 23,441.096525. Trusted source checks/refits
  passed and the independent model reviewer accepted. These synthetic values
  do not establish customer-data accuracy or statistical significance.
- New AgentCore sessions reconnected to the saved datasets/results. A second
  owner did not see the first owner's data. No container-local state was needed.
- Final Excel forecast recorded 3,991 input and 831 output tokens across planner,
  analyst and reviewer. Usage is measured call metadata, not a billing invoice.

[Library smoke](deployment/2026-10-31-library-smoke.json) imported PyArrow 17.0.0,
DuckDB 1.3.2, openpyxl 3.1.3, NumPy 1.26.4, pandas 2.3.1, SciPy 1.16.0,
scikit-learn 1.5.0, statsmodels 0.14.5, Matplotlib 3.9.0 and Plotly 5.22.0 in the
actual managed interpreter. It checked the known data totals and retrieved a
27,625-byte [PNG](cloud-smoke-plot.png). Total smoke time: 6,010.07 ms.
The hosted quick container used PyArrow 23.0.1/DuckDB 1.5.6. Interpreter and
container versions differ; trusted cross-version numerical checks passed.

## Actual safety/lifecycle acceptance

[Cleanup proof](deployment/2026-10-31-cleanup-proof.json) queries session state
and confirms TERMINATED for CSV forecast, Excel forecast, library smoke and a
controlled live cancellation session. Cancellation was triggered after sandbox
start while a sleep was running; cleanup_error was null.

[Live application safety checks](deployment/2026-10-31-safety-acceptance.json):
malformed CSV and competing-sheet workbook rejected/clarified; same request key
returned the same cancelled run; a changed question with that key conflicted;
wrong-owner run access/deletion returned not_found; cancelled run stayed terminal
without a result after eight seconds; deletion survived reconnect; dataset S3
prefix was empty and owner admission lease released.

No failure was interpreted as success. Initial Claude agreement activation,
planner missing metric, overly strict narrative numeric validation, analyst
JSON lambda and missing built-in interpreter metadata were observed and fixed
or explicitly bounded before final acceptance. The analyst policy stayed strict;
a bounded pre-execution repair was added. The exact AWS system interpreter ARN
alone may rely on its documented restrictive defaults when metadata omits network
configuration; custom interpreters still require explicit sandbox/no-role/no-mount
metadata.

## Prior browser proof through the loopback bridge

Playwright MCP at `http://127.0.0.1:8876` exercised automatic Excel upload → chart
→ three-month forecast through the deployed AgentCore runtime. Browser forecast
`b352a1e7f07cccb5047d14e18dc12fb8` completed in 13,545.86 ms with numerical and
independent review. The earlier rejected code-policy run remained visibly failed.
The new success was not substituted into that failed run.

Reload retained the question/dataset and saved results; evidence download
`analysis-b352a1e7.json` completed. The cloud badge identifies the actual backend.
Both 1440 px desktop and 390 px mobile had no horizontal overflow, zero select
controls and labeled upload/question fields. Final console: zero errors and zero
warnings. Earlier keyboard/skip-link focus checks passed on the same UI structure.
This is a responsive/accessibility spot check, not a full assistive-technology audit.

Screenshots: [cloud desktop](workspace-cloud.png), [cloud mobile](workspace-cloud-mobile.png).
The UI host is still a local IAM developer bridge. This proof establishes AWS
analysis and persistence; it does not establish public frontend hosting/auth.

## Earlier local checks retained

Before cloud integration, the local backend passed CSV → chart → forecast,
reload/restart persistence, malformed input, evidence download and independent-row
synthetic regression/classification browser flows. Regression test MAE was about
0.0755; classification balanced accuracy about 0.977. These supervised recipes
remain local-only. The original manual Excel controls were replaced by automatic
preparation; their old selection flow is superseded.

[Local measurements](local-benchmark.json): preparation 122.82 ms, first query
39.90 ms, five later queries median 6.59 ms, three queries after deep admission
median 7.39 ms, fresh-process forecast 747.67 ms. These exclude HTTP and are tiny
fixture observations, not cloud SLOs. Hash-checked local replay reproduced the
forecast without executing downloaded Python. The earlier legacy SQLite read
connection leak was fixed with explicit closing.

## Security and unverified release boundaries

[Actual ECR scan](deployment/2026-10-31-image-scan.json) reports high findings
CVE-2026-84243, CVE-2026-19499 and CVE-2026-5435 in glibc, plus CVE-2026-85091
in zlib. Available apt upgrades were applied in the final image; findings remain.
A scan finding is not proof of application exploitability, and no reachability
clearance is claimed. Remediation or explicit assessment is required for public
release. The nonroot image and bounded analyst execution do not clear findings.

Earlier `npm audit` on unchanged CDK locks: backend three advisories (one high),
AgentCore 29 (four low/twenty moderate/four high/one critical). Highest packages
include Handlebars, brace-expansion, browserslist, js-yaml and zod. Those npm
packages are not in the new runtime image or plain CloudFormation deployment.
No broad dependency upgrade or older CDK packaging repair was performed.

Not verified: production MFA/revocation/request-rate policy, the consulting
website's earlier signing/503 behavior, real customer data, general cloud supervised/research tools, durable
queue recovery, production load/p95/cold-start behavior and a reconciled AWS
invoice. The optional loopback bridge retains its demo identity; the hosted gateway
now derives ownership from verified Cognito claims. Seven-day TTL/lifecycle expiry is asynchronous. No public website files
or legacy runtime configuration were changed by the new deployment.

---

## Historical validation retained from July 5, 2026

# Validation Notes

Last local validation: 2026-07-05

Passed:

```bash
python3 -m unittest \
  tests.test_analysis_method_selection \
  tests.test_analysis_persistence \
  tests.test_deep_worker_diagnostics \
  tests.test_mcp_stdio_contract \
  tests.test_virtual_data_scientist_agent
```

Result: 12 tests passed.

```bash
python3 -m py_compile \
  server.py \
  analysis_engine/method_catalog.py \
  analysis_engine/deep_worker.py \
  mcp_server/server.py \
  mcp_server/tools.py \
  app/VirtualDataScientistAgent/main.py \
  app/VirtualDataScientistAgent/runtime_tools.py \
  aws_backend/lambda_handler.py
```

Result: passed.

```bash
cd aws_backend/cdk
npm ci
npm run build
npx cdk synth
```

Result: backend CDK TypeScript build and synth passed.

Partially validated:

```bash
cd agentcore/cdk
npm ci
npm run build
```

Result: AgentCore CDK TypeScript build passed.

Blocked locally:

```bash
cd agentcore/cdk
npm run cdk -- synth
```

Result: AgentCore CDK synth failed in the generated AgentCore packaging path
while invoking `uv`. First run attempted to inspect the host uv cache outside
the workspace; an isolated-cache rerun failed with a `uv`
`system-configuration` panic. This appears to be a local packaging/tooling
issue, not a TypeScript compile issue.

## November 1 audit and ML Workbench domain migration

- Release `dev-20261101-01`, AgentCore runtime version 17, is deployed in the existing core/web stacks. Both stacks are `UPDATE_COMPLETE`; CloudFront is `Deployed`. No resource was replaced or removed.
- Canonical URL: https://mlworkbench.decision-layer.com/. The analyst and original CloudFront addresses remain supported. A/AAAA aliases, certificate coverage, three Cognito callback/logout URLs, three S3 CORS origins and the gateway allowlist were verified.
- The four reproduced audit defects are fixed; 87 Python tests and 25 Node tests pass. React Flow rebuild matches its committed bundle. JavaScript syntax, Python dependency consistency, production npm audits and AWS template validation pass. The new image scan reports zero critical/high and two previously reviewed medium findings.
- Live authentication/upload acceptance passed on all three origins: secure opaque cookies, reload, logout/replay rejection, rejected cross-origin logout, owner isolation, tamper/oversize rejection and exact 10 MiB preparation/deletion. Temporary synthetic users were removed; credentials stayed in memory. No new model analyses were submitted. The cumulative guard remains at 19/20.
- The local resolver cached an earlier NXDOMAIN answer. The acceptance process used the new hostname's independently published public DNS answer, retaining HTTPS hostname/certificate validation and leaving system DNS/hosts unchanged. After public DNS propagation, the new hostname loaded normally in the browser. Cognito accepted its redirect URI; Back restored the draft and re-enabled sign-in. The synthetic draft was cleared. A screenshot and both old/new-origin browser checks are recorded in the migration verification manifest.

Evidence: [release](deployment/dev-20261101-01.json), [domain](deployment/dev-domain-mlworkbench.json), [authentication/upload checks](deployment/2026-11-01-domain-auth-acceptance.json), [migration verification](deployment/2026-11-01-domain-verification.json), [image scan](deployment/dev-20261101-01-image-scan.json), [audit findings and fixes](audits/2026-11-01-ponytail-audit.md). Earlier real trend/forecast and Transcribe evidence remains historical; it was not rerun for this migration.
