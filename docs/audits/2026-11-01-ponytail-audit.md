What this repo does: Virtual Data Scientist profiles uploaded tables automatically, turns a business question into a checked analysis plan, and produces interactive figures and reproducible evidence. The hosted path uses Cognito, CloudFront, Lambda and an ARM64 container in AWS AgentCore; forecasts execute in a separate AgentCore Code Interpreter session.

Assumed load: a small hosted development preview, a few concurrent users, at most two analyses running globally, ten active datasets per workspace and a twenty-admission development guard. This is a productionization pass, not approval for unrestricted public traffic.

Snapshot reviewed: `9cb1e7427ed66d0582ea893c8f6bc0385afbe2a0`. The audit phase used read-only inspection and local reproductions. Cleanup below was separately authorized by the request to audit and clean up, migrate the subdomain, and commit. Locations refer to the source after cleanup; the reproduction cases failed on the original code.

## Must fix

1. **Active datasets disappear behind deleted history — fixed.**
   - **What this is:** [`CloudStore.items`](../../analysis_engine/cloud_store.py#L51) loads the saved records used for workspace display, upload limits and deletion.
   - **Problem:** It read only the first DynamoDB query page. One hundred deleted dataset records sort before a still-active dataset and make the workspace appear empty; DynamoDB can also split a page at one MiB before reaching one hundred records.
   - **Fix:** Follow `LastEvaluatedKey` until all owner-scoped records have been read, keeping consistent reads and the existing active-dataset limit. The regression creates 101 deleted records before an active dataset.
   - **If we skip it:** Data appears lost and the ten-active-dataset check can undercount storage.

2. **Overlapping upload preparation duplicates a dataset — fixed.**
   - **What this is:** [`CloudService.prepare_upload`](../../analysis_engine/cloud_service.py#L158) and [`CloudStore.upload_slot`](../../analysis_engine/cloud_store.py#L61) prepare an uploaded source and publish an immutable dataset.
   - **Problem:** Two requests for the same upload could both pass the completed-upload lookup before either published. They could create two versions or remove the staged source while the other request was still preparing it. Separate simultaneous uploads could also both pass the ten-dataset check.
   - **Fix:** Serialize preparation per workspace with a conditional DynamoDB lease. A competing request receives a retryable capacity response without touching the source; completed retries return the saved dataset. Release checks a unique lease token, and an abandoned lease can be reclaimed after 420 seconds. Both staged and direct uploads use the lease.
   - **If we skip it:** Network retries can duplicate datasets or fail unpredictably, and the active-dataset limit is not reliable under overlap.

## Should fix

3. **An old trial cookie blocks another account from signing in — fixed.**
   - **What this is:** The [sign-in route](../../aws_backend/web_gateway.py#L112) exchanges a verified Cognito token for a browser session and optionally claims a guest workspace.
   - **Problem:** A guest cookie claimed by account A remains after logout. Account B's valid sign-in created a session and then failed with access denied while trying to claim A's workspace. Anonymous analysis is currently disabled, but this breaks the supported guest-to-member transition when enabled.
   - **Fix:** Allow sign-in to complete when an optional claim is denied because the trial belongs to another account. Explicit claims still reject account B, and B receives no access to A's records. A gateway regression verifies both successful sign-in and continued isolation.
   - **If we skip it:** Users sharing a browser can get stuck at sign-in and leave unused session rows until expiry.

4. **A deployment retry stops at an already-updated stack — fixed.**
   - **What this is:** [`update`](../../scripts/deploy_dev.py#L14) reviews and executes CloudFormation change sets for the existing development stacks.
   - **Problem:** If the core update succeeds and the web update fails, retrying the same command reaches an unchanged core stack. CloudFormation reports an empty change set as failed, and the script aborts before retrying the web update.
   - **Fix:** Recognize only CloudFormation's specific no-changes failure, remove that empty change set and continue with the existing stack. Other failures still raise; resource replacement/removal guards remain. Unique change-set names also avoid collisions during rapid retries.
   - **If we skip it:** Recovery requires manual parameter juggling during a partial deployment.

## Nice to have

5. **Unused chart bundles remain in source — removed.**
   - **What this is:** The old full D3 and Plotly Basic scripts in `static/vendor/`.
   - **Problem:** No current page, source renderer, publisher or test references them. The active app uses ECharts and React Flow, while these extra copies add 1,295,813 bytes and stale provenance to the repository. They were not loaded by the current page, so removal is not claimed as a page-speed improvement.
   - **Fix:** Remove the two scripts and the unused standalone D3 license, then update the current vendor manifest. Keep ECharts notices, React Flow's bundled notices, Python/Plotly export compatibility and React Flow's required transitive D3 packages.
   - **If we skip it:** Future maintainers must keep distinguishing unused copies from actual supported renderers.

Verdict: Fix the four reproduced reliability defects before the domain move. Their regression cases now pass. The requested migration uses the existing distribution, data, identities and runtime; it adds the new canonical domain while retaining the old domain and CloudFront origin for sign-in continuity. A broader rewrite is not justified by this preview's load.

Lean: -23 lines, -2 unused vendored dependencies removed (1,295,813 bytes). No installed package dependency was removed. Necessary fixes and regression coverage increase the handwritten source total.

Not checked: credential-bearing files; exhaustive line-by-line review of the legacy local server and retired runtime; third-party implementation internals beyond the installed Strands usage-counter contract; penetration testing; unrestricted public-load behavior; long-running soak tests; formal statistical validation of additional ML methods not implemented by this app; guaranteed spending caps. The twenty-admission guard is an application guard, not an AWS-enforced dollar cap. Current CloudWatch dashboards and alarms were inspected as infrastructure, not exercised through injected outages.

Validation before deployment: 87 Python tests and 25 JavaScript tests passed; Python dependency consistency passed; both generated CloudFormation templates passed AWS validation. Hosted deployment and final verification are recorded separately in the release manifest and validation log.

Post-deployment: both updated stacks completed without replacements/removals. Live authentication/upload checks passed on all three callback origins, including exact 10 MiB preparation, revoked-cookie replay and origin/owner isolation. No model analyses were submitted and the global admission ledger remains 19/20. New-domain verification used its published public DNS answer while a local negative DNS cache expires, with normal certificate verification. See `docs/deployment/2026-11-01-domain-verification.json` for the final browser state.

Final browser verification: the new hostname loaded normally after public DNS propagation; Cognito accepted the new redirect URI, Back preserved a synthetic draft and sign-in became usable again. The synthetic draft was cleared. The same Back check passed at the retained analyst origin. Implementation commit `55e997d` passed both push and pull-request CI. No extra model job was needed.
