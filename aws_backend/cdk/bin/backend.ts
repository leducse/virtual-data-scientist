#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { VirtualDataScientistBackendStack } from "../lib/backend-stack";

const app = new cdk.App();
const account = process.env.CDK_DEFAULT_ACCOUNT ?? process.env.AWS_ACCOUNT_ID ?? "441383083571";
const region = process.env.CDK_DEFAULT_REGION ?? process.env.AWS_REGION ?? "us-east-1";

new VirtualDataScientistBackendStack(app, "VirtualDataScientistBackend-dev", {
  env: { account, region },
  agentCoreRuntimeRoleArn:
    process.env.AGENTCORE_RUNTIME_ROLE_ARN ??
    "arn:aws:iam::441383083571:role/AgentCore-vdsagentcore-de-ApplicationAgentVirtualDa-kmxwi1bu11PF",
});
