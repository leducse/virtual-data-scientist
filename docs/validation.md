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
