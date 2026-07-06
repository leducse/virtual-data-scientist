# AgentCore Components

This folder tracks the AgentCore deployment path for the Virtual Data Scientist
app.

Current AWS deployment status:

- Account: `441383083571`
- Region: `us-east-1`
- Stack: `AgentCore-vdsagentcore-default`
- Runtime name: `VirtualDataScientistAgent`
- Runtime ID: `vdsagentcore_VirtualDataScientistAgent-iSOiop5y80`
- Runtime ARN:
  `arn:aws:bedrock-agentcore:us-east-1:441383083571:runtime/vdsagentcore_VirtualDataScientistAgent-iSOiop5y80`
- Runtime state: `READY`
- Backend stack: `VirtualDataScientistBackend-dev`
- Backend Function URL:
  `https://fdzrbtz4sewn6nrnlnbgbykbpu0jcutl.lambda-url.us-east-1.on.aws/`
- Backend Lambda: `virtual-data-scientist-backend-dev`
- Analysis state bucket:
  `virtualdatascientistbacke-analysisstatebucket24530-zbt8jnot9lld`
- Latest AgentCore deploy hash: `ae9f334f56d4da30`
- End-to-end smoke status: consulting website upload reaches the authenticated
  backend, persists a CSV as an S3-backed `s3_csv` data source, AgentCore
  invocation profiles that uploaded source, and artifacts are readable through
  the website bridge.

Current components:

- `agentcore/agentcore.json`: deployable AgentCore Runtime config.
- `agentcore/aws-targets.json`: AWS account/region target.
- `agentcore/cdk/`: AgentCore CLI generated CDK wrapper.
- `aws_backend/lambda_handler.py`: Lambda Function URL adapter for the app's
  analysis API.
- `aws_backend/cdk/`: backend S3/Lambda/IAM CDK stack.
- `mcp_server/server.py`: stdio MCP facade exposing data-science tools.
- `mcp_server/tools.py`: tool wrappers over the local BI app API.
- `app/VirtualDataScientistAgent/main.py`: AgentCore entrypoint with HTTP and
  WebSocket handlers.
- `app/VirtualDataScientistAgent/runtime_tools.py`: runtime-local authenticated
  backend wrappers packaged with the AgentCore CodeZip.
- `app/VirtualDataScientistAgent/prompts/`: system and deep-analysis workflow
  prompts.
- `agentcore/runtime-contract.md`: request/response contract shared by the
  website bridge and the AgentCore runtime.

Local validation:

```bash
cd /Users/scottleduc/Projects/virtual-data-scientist
python3 -m unittest tests.test_analysis_method_selection tests.test_analysis_persistence tests.test_deep_worker_diagnostics tests.test_mcp_stdio_contract tests.test_virtual_data_scientist_agent
python3 -m py_compile server.py analysis_engine/method_catalog.py analysis_engine/deep_worker.py mcp_server/server.py mcp_server/tools.py app/VirtualDataScientistAgent/main.py app/VirtualDataScientistAgent/runtime_tools.py
agentcore validate --directory /Users/scottleduc/Projects/virtual-data-scientist --json
agentcore package --directory /Users/scottleduc/Projects/virtual-data-scientist --runtime VirtualDataScientistAgent
```

Backend CDK validation:

```bash
cd /Users/scottleduc/Projects/virtual-data-scientist/aws_backend/cdk
npm run build
npx cdk synth
npx cdk diff
```

Optional end-to-end local validation with the BI backend running:

```bash
python3 server.py
```

MCP stdio smoke test:

```bash
printf '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}\n' \
  | python3 -m mcp_server.server
```

AgentCore CLI notes:

- Use the current `@aws/agentcore` CLI for new work. The older Python
  `bedrock-agentcore-starter-toolkit` is now a legacy workflow.
- CLI version used for the first deploy: `0.22.0`.
- The runtime package must include `aws-opentelemetry-distro`; AgentCore wraps
  the entrypoint with `opentelemetry-instrument` when OTEL is enabled.
- `agentcore/agentcore.json` intentionally uses
  `codeLocation: app/VirtualDataScientistAgent` and `entrypoint: main.py`.
  Do not point CodeZip back at the repository root; generated CDK assets and
  local caches exceed the AgentCore zip limit.
- Deployment command:

```bash
agentcore deploy --target default --yes --json
```

- Status command:

```bash
agentcore status --target default --json
```

- Smoke invocation command:

```bash
agentcore invoke --target default --runtime VirtualDataScientistAgent \
  --session-id 123e4567-e89b-12d3-a456-426614174000 \
  --prompt "Profile the demo sales warehouse orders table and run a deep analysis to identify revenue drivers and risks." \
  --json
```

- Configure the deployed runtime ARN in the consulting website with
  `DATA_SCIENTIST_AGENTCORE_RUNTIME_ARN`.

Remaining public-hosting dependency:

- Configure the public consulting website host with the deployed env vars and an
  AWS identity that can call `bedrock-agentcore:InvokeAgentRuntime` and sign the
  `AWS_IAM` Lambda Function URL. The local website route has been smoke-tested
  against the deployed runtime/backend.
- For production, keep app-owned Postgres/S3 as the source of truth; use
  AgentCore Memory for continuity, not artifact persistence.

Current AgentCore shape:

```text
agentcore/
  agentcore.json
  aws-targets.json
  cdk/
aws_backend/
  lambda_handler.py
  cdk/
app/
  VirtualDataScientistAgent/
mcp_server/
```
