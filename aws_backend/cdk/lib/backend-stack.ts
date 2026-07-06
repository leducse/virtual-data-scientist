import * as path from "path";
import * as cdk from "aws-cdk-lib";
import { Duration, RemovalPolicy } from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";

export interface VirtualDataScientistBackendStackProps extends cdk.StackProps {
  agentCoreRuntimeRoleArn: string;
}

export class VirtualDataScientistBackendStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: VirtualDataScientistBackendStackProps) {
    super(scope, id, props);

    const appRoot = path.resolve(__dirname, "../../../..");
    const stateBucket = new s3.Bucket(this, "AnalysisStateBucket", {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      removalPolicy: RemovalPolicy.RETAIN,
      versioned: true,
    });

    const backendFunction = new lambda.Function(this, "BackendFunction", {
      functionName: "virtual-data-scientist-backend-dev",
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: "aws_backend.lambda_handler.handler",
      code: lambda.Code.fromAsset(appRoot, {
        ignoreMode: cdk.IgnoreMode.GIT,
        exclude: [
          ".env*",
          ".git",
          ".pytest_cache",
          ".venv",
          "__pycache__",
          "**/__pycache__",
          "agentcore",
          "aws_backend/README.md",
          "aws_backend/cdk",
          "data",
          "docs",
          "node_modules",
          "static",
          "tests",
        ],
      }),
      description: "Authenticated backend API for the Virtual Data Scientist AgentCore runtime.",
      timeout: Duration.seconds(120),
      memorySize: 1024,
      tracing: lambda.Tracing.ACTIVE,
      environment: {
        DATA_DIR: "/tmp/virtual-data-scientist",
        ANALYSIS_STORAGE: "s3",
        ANALYSIS_STATE_BUCKET: stateBucket.bucketName,
        ANALYSIS_STATE_PREFIX: "virtual-data-scientist/dev",
        DEEP_ANALYSIS_EXECUTION_MODE: "inline",
        DEEP_ANALYSIS_AGENT_MODE: "agentcore_backend_worker",
      },
    });

    stateBucket.grantReadWrite(backendFunction);

    const functionUrl = backendFunction.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.AWS_IAM,
    });

    const agentRole = iam.Role.fromRoleArn(this, "AgentCoreRuntimeRole", props.agentCoreRuntimeRoleArn, {
      mutable: true,
    });
    agentRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ["lambda:InvokeFunctionUrl"],
        resources: [backendFunction.functionArn],
        conditions: {
          StringEquals: {
            "lambda:FunctionUrlAuthType": "AWS_IAM",
          },
        },
      }),
    );
    agentRole.addToPrincipalPolicy(
      new iam.PolicyStatement({
        actions: ["lambda:InvokeFunction"],
        resources: [backendFunction.functionArn],
      }),
    );

    backendFunction.addPermission("AllowAgentCoreRuntimeFunctionUrlInvoke", {
      principal: new iam.ArnPrincipal(props.agentCoreRuntimeRoleArn),
      action: "lambda:InvokeFunctionUrl",
      functionUrlAuthType: lambda.FunctionUrlAuthType.AWS_IAM,
    });

    new cdk.CfnOutput(this, "BackendFunctionName", {
      value: backendFunction.functionName,
    });
    new cdk.CfnOutput(this, "BackendFunctionUrl", {
      value: functionUrl.url,
    });
    new cdk.CfnOutput(this, "AnalysisStateBucketName", {
      value: stateBucket.bucketName,
    });
  }
}
