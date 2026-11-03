# Hosted development access slice

October 31, 2026. Continue the separate VDS development environment under the
approved $10 initial allowance; preserve the existing site/runtime and its edits.

Goal: open the actual workspace over HTTPS with verified user ownership, with
all preparation/analysis/state still in AgentCore/S3/DynamoDB. This is a restricted
development deployment, not a public production launch. No open signup or email
invitations. Temporary acceptance users are created with invitations suppressed
and removed after bounded tests. No credentials/tokens are saved or logged.

Architecture: private static S3 -> CloudFront; /api/v2/* -> IAM-only Lambda URL
through CloudFront OAC. Cognito authorization code + S256 PKCE in the browser;
access token stays in memory. Gateway verifies issuer/signature/expiry/token use/
client and hashes verified issuer+subject into the owner; payload owner ignored.
A separate header carries the user token because OAC signs Authorization.
Sign-in returns after page reload using the provider session. Logout clears
in-memory access and local dataset selection, then visits provider logout.

Uploads use size-constrained five-minute S3 POST policies and an owner-bound
random incoming key. The runtime prepares the staged object; it never accepts
arbitrary bucket/key paths. This preserves the existing 10 MiB upload cap despite
Lambda's smaller synchronous request limit. No source bytes traverse Lambda.

Expected incremental test cost is small request/storage usage under the existing
allowance, without provisioned compute, NAT or a paid custom domain. No fixed
cost/security service is added. Billing remains unreconciled; no hard-cap claim.
Bound tests to two temporary users, one chart and one forecast.

Acceptance: hostile/expired/wrong-client/id tokens rejected; owner spoof ignored;
no anonymous origin access; S3 policy exact owner key/size; malformed/oversize
staged input rejected; live real-token owner isolation and 10 MiB boundary;
actual hosted browser sign-in redirect, upload/chart/forecast, saved evidence;
all existing tests and strongest cheap browser/compile/package checks.

Security: stable Debian packages still show the four prior CVEs. Pin the base
image when registry access permits, constrain locale environment, and document
remaining reachability limits. Do not call findings fixed without a clean scan.
Rollback: leave original website untouched, retain the prior runtime digest,
review new stack/template separately. Public cutover remains a later decision.
