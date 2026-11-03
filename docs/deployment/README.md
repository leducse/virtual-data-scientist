# October 31 AgentCore development evidence

The JSON files in this directory contain sanitized actual deployment outputs,
synthetic live analytical results, session cleanup checks, safety acceptance,
library/plot proof and ECR scan findings. They contain no credentials or customer
data. The latest image release is dev-20261031-08 with actual hosted Cognito/browser
acceptance. The earlier CSV result is v4 and direct Excel/browser/safety proof is
v5; these are preserved as historical evidence. The same synthetic forecast
passed both versions. Full generated evidence lives under ignored data/ and S3.

Restricted hosted-user authentication is now verified. A public production
release is not implied. See ../validation.md,
../cloud-trial.md and ../../project_context.md for the exact boundaries.

Rollback preparation: the original runtime/public site were never switched, so
they remain available. A dev runtime rollback is a reviewed CloudFormation update
to a previous retained immutable ECR digest with matching release/model resources;
do not delete the retained bucket/table as a rollback step. No rollback execution
or fresh bootstrap replay has been tested. Retained ECR images and data continue
to incur storage; destructive cleanup requires an explicit scope.
