# AgentCore development operations and live proof

Updated October 31, 2026. The user authorized actual AWS development deployment
and selected a $10 initial allowance in account `441383083571`, `us-east-1`.
That authorization covered the separate container runtime, ECR/S3/DynamoDB and
bounded synthetic model/interpreter tests. No public website cutover occurred.
This replaces the earlier unexecuted trial proposal.

## Deployed resources

`docs/deployment/2026-10-31-agentcore-dev.json` records actual outputs and digest.
The stack is `VirtualDataScientistV2Dev`, release `dev-20261031-08`; runtime ARN:

```text
arn:aws:bedrock-agentcore:us-east-1:441383083571:runtime/VirtualDataScientistV2Dev-Tr4IBoExJp
```

The nonroot Linux ARM64 container serves `/ping` and `/invocations` on 8080.
`app/CloudDataScientist/main.py` is the deployed entrypoint. Its tracked async
jobs persist to S3/DynamoDB and use the built-in isolated Code Interpreter.
The legacy runtime is unchanged. IAM is the inbound development auth boundary.

Nova Pro (`us.amazon.nova-pro-v1:0`) completed real structured planning, analyst
code and independent review. Claude Sonnet 4.6 had a Marketplace agreement
activation failure after an initial response. No broad Marketplace permission
was added. The runtime role is scoped to the new data bucket/table/ECR,
approved model profile/US destination ARNs, system interpreter and runtime logs.
The ECR authorization API necessarily uses a wildcard resource.

## Reproduce the bounded acceptance

With an existing authorized AWS SDK session:

```bash
export VDS_RUNTIME_ARN=arn:aws:bedrock-agentcore:us-east-1:441383083571:runtime/VirtualDataScientistV2Dev-Tr4IBoExJp
.venv/bin/python scripts/cloud_acceptance.py --runtime-arn "$VDS_RUNTIME_ARN"
.venv/bin/python scripts/cloud_safety_acceptance.py --runtime-arn "$VDS_RUNTIME_ARN"
.venv/bin/python scripts/cloud_smoke.py
```

Those are review-only. Under an approved spending scope, the executed forms are:

```bash
.venv/bin/python scripts/cloud_acceptance.py --runtime-arn "$VDS_RUNTIME_ARN" --execute --forecast --output data/cloud-csv-acceptance.json
.venv/bin/python scripts/cloud_acceptance.py --runtime-arn "$VDS_RUNTIME_ARN" --execute --forecast --xlsx --output data/cloud-xlsx-acceptance.json
.venv/bin/python scripts/cloud_safety_acceptance.py --runtime-arn "$VDS_RUNTIME_ARN" --execute
.venv/bin/python scripts/cloud_smoke.py --execute --region us-east-1 --model-id us.amazon.nova-pro-v1:0 --interpreter-id aws.codeinterpreter.v1 --output data/cloud-import-plot-smoke.json
```

CSV and renamed Excel both produced 36 months/total 579,060, then three future
predictions with test MAE 304.1711 versus naive 860.0. Excel automatically chose
Transactions/header row two/When Sold/Net Sales. Normal forecast, library smoke
and controlled live cancellation sessions were confirmed TERMINATED. The smoke
imported all ten analytical libraries and retrieved a 27,625-byte PNG.

A generated JSON callback lambda was correctly rejected in an early Excel run.
The final workflow supplies the exact approved wrapper and allows one bounded
repair before execution; the AST boundary was not relaxed. A reviewer numeric
gate was corrected to accept known metrics rounded to two decimals while still
rejecting false metrics and unsupported quantitative claims.

## Build and deployment inputs

`Dockerfile` plus `requirements-demo.lock.txt` define the image; `.dockerignore`
allows only required source. `scripts/render_cloud_stack.py` generates the plain
CloudFormation template in `aws_backend/cloud-dev/template.json`. Deployment is
two-stage: bootstrap without ImageUri, upload an ARM64 OCI archive, then update
with the immutable digest, model resources and release identifier. The deployed
stack does not rely on the older CDK npm dependencies/uv packaging path.

```bash
.venv/bin/python scripts/render_cloud_stack.py
docker buildx build --platform linux/arm64 --provenance=false --output type=oci,dest=/tmp/vds-runtime.oci .
.venv/bin/python scripts/push_ecr.py /tmp/vds-runtime.oci --repository virtual-data-scientist-v2-dev --tag UNIQUE_RELEASE
```

The final command is review-only without `--execute`. It uploads layers through
IAM APIs, without writing Docker registry credentials. Do not reuse immutable
tags or deploy over the legacy runtime. A new deploy must be within the user's
authorized scope and checked using a reviewable template/change set.

Runtime idle/max lifetime: 60/900 seconds. Sandbox max execution: 120 seconds.
S3 and DDB retention: seven-day asynchronous lifecycle/TTL; logs: seven days.
No always-on VM, NAT gateway or provisioned database instance was created.
ECR images and retained stack data remain until explicit cleanup.

## Cost evidence and public release boundary

The $10 allowance is an operational limit, not an enforced AWS budget cap.
Successful per-role token counts, sandbox timings and release lineage are in
live acceptance evidence. Failed model responses can lack usage metadata; these
records are not a complete billing invoice. Current billed spend has not been
reconciled. Do not claim an exact dollar total or a hard cost cap from them.

The hosted development UI now uses CloudFront, Cognito PKCE and a verified-user
Lambda gateway. See `hosted-development-access.md` and deployment evidence. The
loopback developer bridge remains optional. A public production release still
needs MFA/revocation/rate policy, image remediation, website integration and a
release diff/rollback plan. No public website auth/503 fix is
claimed. The final image scan retains four high, nine medium and three low OS
findings after available upgrades; resolve or explicitly assess reachability and
risk before public release. General cloud regression/classification, researcher
citations, crash-resumable queue and production load/accuracy proof remain work.

## References checked

- [Custom container deployment](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/getting-started-custom.html)
- [Runtime HTTP contract](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html)
- [Code Interpreter API](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-agentcore/client/invoke_code_interpreter.html)
- [Strands structured output](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/agents/structured-output/)
- [AgentCore pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)
