# AWS Backend

This folder contains the AWS backend adapter used by the deployed Virtual Data
Scientist AgentCore runtime.

Deployed development stack:

- Stack: `VirtualDataScientistBackend-dev`
- Account: `441383083571`
- Region: `us-east-1`
- Lambda: `virtual-data-scientist-backend-dev`
- Function URL:
  `https://fdzrbtz4sewn6nrnlnbgbykbpu0jcutl.lambda-url.us-east-1.on.aws/`
- Auth: `AWS_IAM`
- State bucket:
  `virtualdatascientistbacke-analysisstatebucket24530-zbt8jnot9lld`

The Lambda handler exposes only the analysis/API routes needed by the MCP
facade and consulting website bridge. It does not serve the local static UI.

Cloud CSV upload is live at `POST /api/csv/upload`. In deployed mode the backend
stores the raw CSV in the analysis state bucket, registers a persisted `s3_csv`
data source in `analysis_sessions.json`, materializes the uploaded table in
Lambda `/tmp` when needed, and returns schema metadata plus the new
`data_source_id`.

Validation:

```bash
cd /Users/scottleduc/Projects/virtual-data-scientist
python3 -m py_compile server.py mcp_server/tools.py aws_backend/lambda_handler.py
python3 -m unittest tests.test_analysis_method_selection tests.test_analysis_persistence tests.test_deep_worker_diagnostics tests.test_mcp_stdio_contract tests.test_virtual_data_scientist_agent

cd /Users/scottleduc/Projects/virtual-data-scientist/aws_backend/cdk
npm run build
npx cdk synth
npx cdk diff
```

Deploy:

```bash
cd /Users/scottleduc/Projects/virtual-data-scientist/aws_backend/cdk
npx cdk deploy --require-approval never --outputs-file cdk-outputs.json
```

Smoke test:

```bash
aws lambda invoke \
  --function-name virtual-data-scientist-backend-dev \
  --cli-binary-format raw-in-base64-out \
  --payload '{"requestContext":{"http":{"method":"GET"}},"rawPath":"/api/health","rawQueryString":""}' \
  /tmp/vds-backend-health.json
```

CSV upload smoke test:

```bash
aws lambda invoke \
  --function-name virtual-data-scientist-backend-dev \
  --cli-binary-format raw-in-base64-out \
  --payload '{"rawPath":"/api/csv/upload","requestContext":{"http":{"method":"POST"}},"body":"{\"name\":\"agentcore_smoke_upload\",\"csv_text\":\"customer_id,churn,monthly_fee\\n1,0,99.5\\n2,1,49.0\\n3,0,79.0\\n\"}"}' \
  /tmp/vds-lambda-upload.json
```
