Historical local workbench instructions preserved on October 31, 2026. Cloud deployment statements below have not been reverified during this build. See the root README for the current application.

# Virtual Data Scientist

Virtual Data Scientist is a portfolio-grade agentic analytics app for helping
business users decide what analysis to run, execute a fast first pass, and hand
off heavier work to an AWS AgentCore runtime while preserving code, artifacts,
and session context.

The core product loop is:

```text
upload or connect data -> run light analysis -> request deep analysis
-> persist code/artifacts/context -> continue the analysis later
```

![Virtual Data Scientist architecture](docs/architecture/virtual-data-scientist-architecture.svg)

## What This Repo Contains

- `server.py`: local standard-library HTTP app with demo warehouse, CSV upload,
  report routes, and analysis APIs.
- `analysis_engine/`: method selection, light-analysis profiling, and
  dependency-light deep-analysis diagnostics.
- `mcp_server/`: stdio MCP facade for sessions, upload, light analysis, deep
  analysis, status, artifacts, and continuation.
- `app/VirtualDataScientistAgent/`: AWS AgentCore runtime entrypoint and
  runtime-local backend tools.
- `aws_backend/`: IAM-protected Lambda Function URL backend plus CDK stack for
  S3-backed analysis state.
- `agentcore/`: AgentCore runtime config, example AWS target config, generated
  CDK wrapper, and runtime contract docs.
- `static/`: local development UI.
- `tests/`: focused unit and contract tests for analysis behavior, persistence,
  MCP, and AgentCore response shape.

## Current Status

Working locally:

- SQLite demo warehouse.
- CSV upload into queryable local tables.
- Light analysis with schema/profile summaries, candidate method selection,
  warnings, report artifacts, and generated reproduction code.
- Deep-analysis request flow with a local async worker, method-selection report,
  quality gates, baseline diagnostics, and generated code artifacts.
- Stdio MCP tool facade.
- AgentCore runtime entrypoint contract tests.

Already deployed once in AWS:

- AgentCore runtime: `VirtualDataScientistAgent`
- Authenticated Lambda backend: `virtual-data-scientist-backend-dev`
- S3-backed analysis state bucket

Known current blocker:

- The consulting website demo page is live, but its Next.js API routes on
  Amplify SSR are not receiving usable AWS credentials, so they cannot sign
  calls to AgentCore or the IAM-protected Lambda Function URL yet. The next
  clean fix is either resolving Amplify SSR credential access or moving the
  signing bridge into a small Lambda/API Gateway proxy with its own execution
  role.

## Run Locally

```bash
python3 server.py
```

Open:

```text
http://127.0.0.1:8765
```

The local app works without cloud credentials. Optional integrations are enabled
only when their environment variables and dependencies are configured.

## Validate

Current validation status is tracked in `docs/validation.md`.

```bash
python3 -m unittest \
  tests.test_analysis_method_selection \
  tests.test_analysis_persistence \
  tests.test_deep_worker_diagnostics \
  tests.test_mcp_stdio_contract \
  tests.test_virtual_data_scientist_agent
```

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

CDK validation:

```bash
cd aws_backend/cdk
npm install
npm run build
npx cdk synth
```

```bash
cd agentcore/cdk
npm install
npm run build
npx cdk synth
```

## MCP Smoke Test

```bash
printf '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}\n' \
  | python3 -m mcp_server.server
```

## Optional Real-Service Setup

Install optional dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 server.py
```

Optional Bedrock report generation:

```bash
export AGENT_MODE=auto
export AWS_REGION=us-east-1
export BEDROCK_MODEL_ID="your-bedrock-model-or-inference-profile-id"
```

Optional Postgres source:

```bash
export POSTGRES_NAME="Warehouse Postgres"
export POSTGRES_HOST="example.cluster.region.rds.amazonaws.com"
export POSTGRES_PORT=5432
export POSTGRES_DATABASE="analytics"
export POSTGRES_USER="readonly_report_user"
export POSTGRES_PASSWORD="..."
export POSTGRES_SSLMODE=require
```

Optional S3 CSV upload:

```bash
export CSV_STORAGE=s3
export S3_UPLOAD_BUCKET="your-bucket"
export S3_UPLOAD_PREFIX="virtual-data-scientist/uploads"
```

## Safety Boundaries

- Do not commit `.env`, AWS credentials, raw user datasets, analysis artifacts,
  generated AgentCore zip packages, CDK `dist/`, `cdk.out/`, or `node_modules/`.
- Treat deployed AWS commands as explicit-approval operations.
- Keep application storage as the source of truth for analytical artifacts.
  AgentCore Memory should improve continuity, not replace durable audit state.
- Keep the public demo route demo-safe until auth, tenant isolation, quotas,
  upload controls, and artifact access checks are implemented.

## Next Steps

1. Move the website signing bridge out of Amplify SSR if SSR role credentials
   remain unavailable.
2. Add auth and per-user analysis-session ownership.
3. Add quotas, upload size/type limits, and artifact access controls.
4. Expand deep analysis from dependency-light diagnostics to optional
   package-backed model baselines.
5. Add AgentCore Memory/Gateway once tenant boundaries and artifact persistence
   are production-ready.
