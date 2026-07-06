# Virtual Data Scientist Project Context

## Purpose And Current Status

Virtual Data Scientist is an agentic analytics product that helps a user upload
or connect data, get a quick first-pass analysis, and hand heavier analytical
work to an AWS AgentCore runtime. The product is meant to solve the common
workforce gap where people have data and questions but do not know which
statistical or machine-learning technique fits the problem.

Project mode: portfolio with a productionization path.

Current status:

- Local backend and development UI run from `server.py`.
- Analysis engine supports light analysis, method recommendation, and
  dependency-light deep-analysis diagnostics.
- MCP stdio facade exists in `mcp_server/`.
- AgentCore runtime entrypoint exists in `app/VirtualDataScientistAgent/`.
- AWS backend Lambda/CDK exists in `aws_backend/`.
- AgentCore runtime config/CDK wrapper exists in `agentcore/`.
- The consulting website route can host the public demo, but its current
  Amplify SSR API bridge is blocked on runtime AWS credential availability.

## Architecture Map

```text
Browser or LLM client
  -> Website/API client
  -> MCP/API facade
  -> Light analysis engine
  -> Deep analysis queue/runtime path
  -> AgentCore runtime
  -> Authenticated AWS backend
  -> App state store and artifact store
```

Primary architecture asset:

- `docs/architecture/virtual-data-scientist-architecture.svg`
- `docs/architecture/virtual-data-scientist-architecture.mmd`

## Key Logic Map

- `server.py`: local HTTP app, demo warehouse, CSV upload, report routes,
  analysis-session routes, and local development UI endpoints.
- `analysis_engine/method_catalog.py`: problem-type and method recommendation
  logic.
- `analysis_engine/deep_worker.py`: asynchronous local deep-analysis worker and
  diagnostic artifact generation.
- `mcp_server/server.py`: JSON-RPC stdio MCP server.
- `mcp_server/tools.py`: MCP tool wrappers over the local app API.
- `app/VirtualDataScientistAgent/main.py`: AgentCore HTTP/WebSocket entrypoint.
- `app/VirtualDataScientistAgent/runtime_tools.py`: runtime-local wrappers for
  the authenticated backend.
- `aws_backend/lambda_handler.py`: Lambda Function URL adapter for the analysis
  API.
- `aws_backend/cdk/`: CDK stack for Lambda, IAM, and S3-backed state.
- `agentcore/agentcore.json`: AgentCore runtime config.
- `agentcore/runtime-contract.md`: request/response contract shared by website
  bridge and AgentCore runtime.
- `tests/`: focused local tests for analysis, persistence, MCP, and AgentCore
  contract behavior.

## Data Flow

1. User uploads or selects a dataset.
2. Backend registers a dataset and stores metadata.
3. Light analysis profiles shape, types, missingness, cardinality, candidate
   methods, warnings, report artifacts, and reproduction code.
4. Deep analysis receives session id, dataset id, user question, light-analysis
   artifacts, and constraints.
5. AgentCore runtime or the local worker performs longer-running diagnostics.
6. Generated reports, code, and metadata are persisted as artifacts.
7. The user can resume the same session later and continue with the saved
   context.

## External Dependencies

- Python 3.13 for the current local/runtime package.
- Optional `boto3` for Bedrock/S3 integrations.
- Optional `psycopg` for Postgres data sources.
- AWS AgentCore for deployed async runtime.
- AWS Lambda Function URL for the deployed authenticated backend.
- S3 for deployed analysis state and uploaded CSVs.
- CDK/Node for infrastructure synthesis.

## Validation Commands

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

```bash
cd aws_backend/cdk && npm run build && npx cdk synth
```

```bash
cd agentcore/cdk && npm run build && npx cdk synth
```

## Architecture Decisions And Tradeoffs

- Keep MCP/API tools small and stable rather than exposing every internal
  helper as a public tool.
- Split light analysis from deep analysis so the user gets quick value before a
  long-running agent job.
- Keep app-owned state and artifacts as the source of truth. AgentCore Memory is
  for continuity, not audit or artifact persistence.
- Keep local mode dependency-light so the demo runs without AWS credentials.
- Use AWS IAM for deployed backend calls instead of exposing a public unauthenticated
  analysis backend.
- Treat the consulting website as a client/demo surface, not the product repo.

## Known Risks And Next Iterations

- The public website bridge currently needs a better AWS credential/signing
  boundary.
- Auth, tenant isolation, per-user ownership, quotas, upload controls, and
  artifact access checks are not production-ready yet.
- Deep analysis currently uses dependency-light diagnostics, not full
  package-backed model training.
- AgentCore Memory and Gateway should wait until app-owned persistence and
  tenant boundaries are ready.
- Public copy should avoid implying production readiness until access controls
  and reliability work are complete.

## Principal Engineer Explanation

This repo separates the analytical control plane from the website shell. The app
owns sessions, datasets, runs, artifacts, and audit state. MCP exposes a narrow
facade over that application contract. Light analysis is synchronous and bounded;
deep analysis is asynchronous and can run through AgentCore. Reproducibility
comes from persisted artifacts and generated code, not from model memory.

## Undergraduate Explanation

The app looks at a dataset, gives a fast summary, suggests useful analysis
methods, and can run a more detailed analysis later. It saves the results and
the code it used so someone can come back to the same analysis and keep working.
The MCP layer is the tool interface, and AgentCore is the cloud runtime for
longer agent work.

## Non-Technical Explanation

This is a virtual data scientist. A user gives it data and a question, and it
helps decide what kind of analysis makes sense. It starts with quick insights,
then can do deeper work in the background and keep the results organized for
later follow-up.
