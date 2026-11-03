# Development image review — October 31, 2026

Release dev-20261031-15 uses immutable image
`sha256:dd88f551cb3dfe6a077b9d4eed1d553bb1a25d39e361beec83bd1203d38f974d`.
Its pinned AWS Python 3.13 ARM64 base uses Amazon Linux 2023. OS packages were
upgraded during build, the Lambda entrypoint was cleared for AgentCore HTTP,
and the application runs as UID 10001. Imports, dependency consistency,
`/ping`/`/invocations`, forecast/refit and actual AgentCore execution passed.

The final ECR basic scan completed with zero reported critical/high findings and
two medium findings, replacing the previous Debian image's four high findings.
This is a point-in-time OS scan, not a complete dependency or security clearance.
The new streaming npm lockfile audit reports zero vulnerabilities. Older unused
CDK toolchains remain separate repository debt.

| Finding | Current assessment |
|---|---|
| CVE-2026-114406, system CA package | The scan reports weak intermediate-certificate trust risk. The actual image was checked: the AWS SDK selects the packaged certifi CA bundle. This narrows exposure for the application's SDK calls; it does not establish that every possible system TLS consumer is unaffected. Track upstream remediation. |
| CVE-2026-76781, libxml2 catalog parsing | The scan reports denial of service through a malformed XML catalog. The image check confirmed openpyxl's lxml backend is disabled. Hosted code does not accept catalog paths or arbitrary local code. This is a reachability assessment, not a proof that the package is universally safe. Track upstream remediation. |

Detailed findings: [final scan](dev-v2-image-scan-15.json). Vendor CVE pages could
not be retrieved in this pass, so the finding descriptions come from the actual
AWS scan and mitigation observations from the running image.

The application remains an invited-account development deployment. Anonymous
trial creation and self-signup are off; their code was exercised in a temporary
IAM-only acceptance function. Public launch still needs upload/signup/audio abuse
controls, an explicit ongoing spending policy, retention/recovery review and
production authentication decisions. The $10 development allowance has not been
silently converted into an unbounded public-service budget.
