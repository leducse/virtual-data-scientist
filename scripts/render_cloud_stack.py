"""Render the bounded development stack without invoking AWS."""
import json
from pathlib import Path


def template():
    sub=lambda text:{'Fn::Sub':text}
    get=lambda name,attr:{'Fn::GetAtt':[name,attr]}
    resources={
        'Images':{'Type':'AWS::ECR::Repository','DeletionPolicy':'Retain','Properties':{
            'RepositoryName':'virtual-data-scientist-v2-dev','ImageTagMutability':'IMMUTABLE',
            'ImageScanningConfiguration':{'ScanOnPush':True},'EncryptionConfiguration':{'EncryptionType':'AES256'}}},
        'Data':{'Type':'AWS::S3::Bucket','DeletionPolicy':'Retain','UpdateReplacePolicy':'Retain','Properties':{
            'PublicAccessBlockConfiguration':{'BlockPublicAcls':True,'BlockPublicPolicy':True,'IgnorePublicAcls':True,'RestrictPublicBuckets':True},
            'BucketEncryption':{'ServerSideEncryptionConfiguration':[{'ServerSideEncryptionByDefault':{'SSEAlgorithm':'AES256'}}]},
            'CorsConfiguration':{'Fn::If':['HasWebOrigin',{'CorsRules':[{'AllowedOrigins':[{'Ref':'WebOrigin'},{'Fn::If':['HasAlternateOrigin',{'Ref':'AlternateOrigin'},{'Ref':'AWS::NoValue'}]}],'AllowedMethods':['POST'],'AllowedHeaders':['*'],'ExposedHeaders':['ETag'],'MaxAge':300}]},{'Ref':'AWS::NoValue'}]},
            'LifecycleConfiguration':{'Rules':[{'Id':'DevelopmentRetention','Status':'Enabled','ExpirationInDays':7,'AbortIncompleteMultipartUpload':{'DaysAfterInitiation':1}}]}}},
        'DataPolicy':{'Type':'AWS::S3::BucketPolicy','Properties':{'Bucket':{'Ref':'Data'},'PolicyDocument':{'Version':'2012-10-17','Statement':[
            {'Effect':'Deny','Principal':'*','Action':'s3:*','Resource':[get('Data','Arn'),sub('${Data.Arn}/*')],'Condition':{'Bool':{'aws:SecureTransport':'false'}}}]}}},
        'State':{'Type':'AWS::DynamoDB::Table','DeletionPolicy':'Retain','Properties':{
            'BillingMode':'PAY_PER_REQUEST','AttributeDefinitions':[{'AttributeName':'pk','AttributeType':'S'},{'AttributeName':'sk','AttributeType':'S'}],
            'KeySchema':[{'AttributeName':'pk','KeyType':'HASH'},{'AttributeName':'sk','KeyType':'RANGE'}],
            'SSESpecification':{'SSEEnabled':True},'TimeToLiveSpecification':{'AttributeName':'expires_at','Enabled':True}}},
        'RuntimeRole':{'Type':'AWS::IAM::Role','Properties':{'RoleName':'VdsV2DevRuntimeRole',
            'AssumeRolePolicyDocument':{'Version':'2012-10-17','Statement':[{'Effect':'Allow','Principal':{'Service':'bedrock-agentcore.amazonaws.com'},'Action':'sts:AssumeRole',
                'Condition':{'StringEquals':{'aws:SourceAccount':{'Ref':'AWS::AccountId'}},'ArnLike':{'aws:SourceArn':sub('arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:runtime/*')}}}]},
            'Policies':[{'PolicyName':'VdsDevelopmentDataAndExecution','PolicyDocument':{'Version':'2012-10-17','Statement':[
                {'Effect':'Allow','Action':['s3:GetObject','s3:PutObject','s3:DeleteObject'],'Resource':sub('${Data.Arn}/*')},
                {'Effect':'Allow','Action':['s3:ListBucket'],'Resource':get('Data','Arn')},
                {'Effect':'Allow','Action':['dynamodb:GetItem','dynamodb:PutItem','dynamodb:UpdateItem','dynamodb:DeleteItem','dynamodb:Query'],'Resource':get('State','Arn')},
                {'Effect':'Allow','Action':['ecr:BatchGetImage','ecr:GetDownloadUrlForLayer','ecr:BatchCheckLayerAvailability'],'Resource':get('Images','Arn')},
                {'Effect':'Allow','Action':['ecr:GetAuthorizationToken'],'Resource':'*'},
                {'Effect':'Allow','Action':['bedrock:InvokeModel','bedrock:InvokeModelWithResponseStream'],'Resource':{'Ref':'ModelResources'}},
                {'Effect':'Allow','Action':['bedrock-agentcore:StartCodeInterpreterSession','bedrock-agentcore:InvokeCodeInterpreter','bedrock-agentcore:StopCodeInterpreterSession'],
                 'Resource':sub('arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:aws:code-interpreter/aws.codeinterpreter.v1')},
                {'Effect':'Allow','Action':['logs:CreateLogGroup','logs:CreateLogStream','logs:PutLogEvents','logs:DescribeLogStreams'],
                 'Resource':sub('arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/bedrock-agentcore/runtimes/VirtualDataScientistV2Dev*')}
            ]}}]}},
        'Runtime':{'Type':'AWS::BedrockAgentCore::Runtime','Condition':'HasImage','Properties':{
            'AgentRuntimeName':'VirtualDataScientistV2Dev','AgentRuntimeArtifact':{'ContainerConfiguration':{'ContainerUri':{'Ref':'ImageUri'}}},
            'RoleArn':get('RuntimeRole','Arn'),'NetworkConfiguration':{'NetworkMode':'PUBLIC'},'ProtocolConfiguration':'HTTP',
            'LifecycleConfiguration':{'IdleRuntimeSessionTimeout':60,'MaxLifetime':900},
            'EnvironmentVariables':{'VDS_DATA_BUCKET':{'Ref':'Data'},'VDS_STATE_TABLE':{'Ref':'State'},'VDS_MODEL_ID':{'Ref':'ModelId'},'VDS_RELEASE':{'Ref':'ReleaseId'}}}}
    }
    metric_base=['DecisionLayer/VDS','stage_events','environment','development','stage','analysis','status']
    widgets=[
        {'type':'text','x':0,'y':0,'width':24,'height':2,'properties':{'markdown':'# VDS development operations\nPrivate operator view. Low-volume rates need sample counts. No traffic is not a successful analysis. Usage is not reconciled billing. Logs exclude analysis content.'}},
        {'type':'metric','x':0,'y':2,'width':12,'height':6,'properties':{'title':'Terminal analysis events','region':{'Ref':'AWS::Region'},'period':300,'stat':'Sum','metrics':[metric_base+[s,{'label':s}] for s in ['completed','failed','cancelled']]}},
        {'type':'metric','x':12,'y':2,'width':12,'height':6,'properties':{'title':'Completed analysis duration (milliseconds)','region':{'Ref':'AWS::Region'},'period':300,
            'metrics':[['DecisionLayer/VDS','duration_ms','environment','development','stage','analysis','status','completed',{'stat':stat,'label':stat}] for stat in ['p50','p95','SampleCount']]}},
        {'type':'metric','x':0,'y':8,'width':12,'height':6,'properties':{'title':'Web gateway errors and throttles','region':{'Ref':'AWS::Region'},'period':300,'stat':'Sum',
            'metrics':[['AWS/Lambda',name,'FunctionName','vds-v2-dev-web'] for name in ['Errors','Throttles']]}},
        {'type':'metric','x':12,'y':8,'width':12,'height':6,'properties':{'title':'Web gateway duration','region':{'Ref':'AWS::Region'},'period':300,'stat':'p95',
            'metrics':[['AWS/Lambda','Duration','FunctionName','vds-v2-dev-web']]}},
        {'type':'log','x':0,'y':14,'width':24,'height':7,'properties':{'title':'Stage durations and quality gate outcomes (content-free)','region':{'Ref':'AWS::Region'},'view':'table',
            'query':"SOURCE logGroups(namePrefix: ['/aws/bedrock-agentcore/runtimes/VirtualDataScientistV2Dev']) | filter service = 'vds' | stats count(*) as events, pct(duration_ms, 95) as p95_ms by stage, status | sort stage asc"}},
        {'type':'log','x':0,'y':21,'width':24,'height':6,'properties':{'title':'Recent operational errors','region':{'Ref':'AWS::Region'},'view':'table',
            'query':"SOURCE logGroups(namePrefix: ['/aws/bedrock-agentcore/runtimes/VirtualDataScientistV2Dev']) | filter event = 'dependency_error' | fields @timestamp, run_id, stage, error_code | sort @timestamp desc | limit 30"}}
    ]
    # Intrinsics inside DashboardBody must be resolved by Fn::Sub, not JSON objects.
    for widget in widgets:
        if widget['type']!='text':widget['properties']['region']='${AWS::Region}'
    resources['Dashboard']={'Type':'AWS::CloudWatch::Dashboard','Condition':'HasImage','Properties':{
        'DashboardName':'vds-v2-development','DashboardBody':sub(json.dumps({'start':'-PT3H','periodOverride':'inherit','widgets':widgets}))}}
    resources['AnalysisFailures']={'Type':'AWS::CloudWatch::Alarm','Properties':{
        'AlarmName':'vds-v2-dev-analysis-failures','AlarmDescription':'Three failed analyses in five minutes. Inspect the private dashboard and correlate run IDs; never blindly replay unknown executions.',
        'Namespace':'DecisionLayer/VDS','MetricName':'stage_events','Dimensions':[{'Name':k,'Value':v} for k,v in [('environment','development'),('stage','analysis'),('status','failed')]],
        'Statistic':'Sum','Period':300,'EvaluationPeriods':1,'Threshold':3,'ComparisonOperator':'GreaterThanOrEqualToThreshold','TreatMissingData':'notBreaching'}}
    widgets.append({'type':'log','x':0,'y':27,'width':24,'height':6,'properties':{'title':'Measured model usage by role (not a bill)','region':'${AWS::Region}','view':'table',
        'query':"SOURCE logGroups(namePrefix: ['/aws/bedrock-agentcore/runtimes/VirtualDataScientistV2Dev']) | filter event = 'model_usage' | stats sum(input_tokens) as input_tokens, sum(output_tokens) as output_tokens, count(*) as measured_calls by stage"}})
    # Re-serialize after adding the usage view.
    resources['Dashboard']['Properties']['DashboardBody']=sub(json.dumps({'start':'-PT3H','periodOverride':'inherit','widgets':widgets}))
    return {'AWSTemplateFormatVersion':'2010-09-09','Description':'Virtual Data Scientist isolated container development environment',
        'Parameters':{'ImageUri':{'Type':'String','Default':''},'ModelId':{'Type':'String','Default':'us.amazon.nova-pro-v1:0'},
                      'ModelResources':{'Type':'CommaDelimitedList'},'ReleaseId':{'Type':'String','Default':'dev-v2'},'WebOrigin':{'Type':'String','Default':''},'AlternateOrigin':{'Type':'String','Default':''}},
        'Conditions':{'HasAlternateOrigin':{'Fn::Not':[{'Fn::Equals':[{'Ref':'AlternateOrigin'},'']}]},'HasImage':{'Fn::Not':[{'Fn::Equals':[{'Ref':'ImageUri'},'']}]},'HasWebOrigin':{'Fn::Not':[{'Fn::Equals':[{'Ref':'WebOrigin'},'']}]}},'Resources':resources,
        'Outputs':{'DataBucket':{'Value':{'Ref':'Data'}},'StateTable':{'Value':{'Ref':'State'}},'ImageRepository':{'Value':get('Images','RepositoryUri')},
                   'RuntimeArn':{'Condition':'HasImage','Value':get('Runtime','AgentRuntimeArn')}}}


def main():
    document=template()
    assert document['Resources']['Runtime']['Condition']=='HasImage'
    assert document['Resources']['State']['Properties']['BillingMode']=='PAY_PER_REQUEST'
    Path('aws_backend/cloud-dev/template.json').write_text(json.dumps(document,indent=2)+'\n')


if __name__=='__main__':main()
