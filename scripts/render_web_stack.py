"""Render an isolated, restricted-user HTTPS development workspace stack."""
import json
from pathlib import Path


def template():
    ref = lambda name: {'Ref': name}
    attr = lambda name, key: {'Fn::GetAtt': [name, key]}
    sub = lambda value: {'Fn::Sub': value}
    resources = {
        'Site': {'Type': 'AWS::S3::Bucket', 'DeletionPolicy': 'Retain', 'Properties': {
            'PublicAccessBlockConfiguration': {k: True for k in ['BlockPublicAcls', 'BlockPublicPolicy', 'IgnorePublicAcls', 'RestrictPublicBuckets']},
            'BucketEncryption': {'ServerSideEncryptionConfiguration': [{'ServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]}}},
        'Users': {'Type': 'AWS::Cognito::UserPool', 'DeletionPolicy': 'Retain', 'Properties': {
            'UserPoolName': 'VdsV2DevUsers', 'UserPoolTier': 'LITE', 'DeletionProtection': 'ACTIVE',
            'AdminCreateUserConfig': {'AllowAdminCreateUserOnly': {'Fn::If':['HasPreview',False,True]}},
            'AutoVerifiedAttributes':['email'],
            'Policies': {'PasswordPolicy': {'MinimumLength': 14, 'RequireLowercase': True, 'RequireUppercase': True, 'RequireNumbers': True, 'RequireSymbols': True}},
            'MfaConfiguration': 'OFF'}},
        'Client': {'Type': 'AWS::Cognito::UserPoolClient', 'Properties': {
            'UserPoolId': ref('Users'), 'ClientName': 'vds-dev-browser', 'GenerateSecret': False,
            'AllowedOAuthFlowsUserPoolClient': True, 'AllowedOAuthFlows': ['code'],
            'AllowedOAuthScopes': ['openid', 'profile'], 'SupportedIdentityProviders': ['COGNITO'],
            'CallbackURLs': {'Fn::If':['HasDomain',[sub('${AppOrigin}/'),sub('${LegacyOrigin}/')],[sub('${AppOrigin}/')]]},
            'LogoutURLs': {'Fn::If':['HasDomain',[sub('${AppOrigin}/'),sub('${LegacyOrigin}/')],[sub('${AppOrigin}/')]]},
            'ExplicitAuthFlows': ['ALLOW_ADMIN_USER_PASSWORD_AUTH', 'ALLOW_REFRESH_TOKEN_AUTH'],
            'PreventUserExistenceErrors': 'ENABLED', 'EnableTokenRevocation': True,
            'AccessTokenValidity': 15, 'IdTokenValidity': 15, 'RefreshTokenValidity': 1,
            'TokenValidityUnits': {'AccessToken': 'minutes', 'IdToken': 'minutes', 'RefreshToken': 'days'}}},
        'LoginDomain': {'Type': 'AWS::Cognito::UserPoolDomain', 'Properties': {
            'UserPoolId': ref('Users'), 'Domain': sub('vds-v2-dev-${AWS::AccountId}')}},
        'GatewayRole': {'Type': 'AWS::IAM::Role', 'Properties': {
            'AssumeRolePolicyDocument': {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Principal': {'Service': 'lambda.amazonaws.com'}, 'Action': 'sts:AssumeRole'}]},
            'Policies': [{'PolicyName': 'HostedWorkspace', 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [
                {'Effect': 'Allow', 'Action': ['bedrock-agentcore:InvokeAgentRuntime'], 'Resource': [ref('RuntimeArn'), sub('${RuntimeArn}/runtime-endpoint/DEFAULT')]},
                {'Effect': 'Allow', 'Action': ['s3:PutObject'], 'Resource': sub('arn:${AWS::Partition}:s3:::${DataBucket}/*/incoming/*')},
                {'Effect':'Allow','Action':['dynamodb:GetItem','dynamodb:PutItem','dynamodb:UpdateItem','dynamodb:DeleteItem'],
                 'Resource':sub('arn:${AWS::Partition}:dynamodb:${AWS::Region}:${AWS::AccountId}:table/${StateTable}')},
                {'Effect': 'Allow', 'Action': ['logs:CreateLogStream', 'logs:PutLogEvents'], 'Resource': sub('arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/vds-v2-dev-web:*')}
            ]}}]}},
        'Logs': {'Type': 'AWS::Logs::LogGroup', 'Properties': {'LogGroupName': '/aws/lambda/vds-v2-dev-web', 'RetentionInDays': 7}},
        'Gateway': {'Type': 'AWS::Lambda::Function', 'DependsOn': 'Logs', 'Properties': {
            'FunctionName': 'vds-v2-dev-web', 'Runtime': 'python3.13', 'Architectures': ['arm64'],
            'Handler': 'web_gateway.handler', 'Role': attr('GatewayRole', 'Arn'),
            'Code': {'S3Bucket': ref('DataBucket'), 'S3Key': ref('CodeKey')},
            'Timeout': 75, 'MemorySize': 256,
            'Environment': {'Variables': {'VDS_RUNTIME_ARN': ref('RuntimeArn'), 'VDS_DATA_BUCKET': ref('DataBucket'),
                'VDS_ISSUER': sub('https://cognito-idp.${AWS::Region}.amazonaws.com/${Users}'), 'VDS_CLIENT_ID': ref('Client')}}}},
        'GatewayUrl': {'Type': 'AWS::Lambda::Url', 'Properties': {'TargetFunctionArn': ref('Gateway'), 'AuthType': 'AWS_IAM'}},
        'StaticOac': {'Type': 'AWS::CloudFront::OriginAccessControl', 'Properties': {'OriginAccessControlConfig': {
            'Name': 'vds-v2-dev-static', 'OriginAccessControlOriginType': 's3', 'SigningBehavior': 'always', 'SigningProtocol': 'sigv4'}}},
        'GatewayOac': {'Type': 'AWS::CloudFront::OriginAccessControl', 'Properties': {'OriginAccessControlConfig': {
            'Name': 'vds-v2-dev-gateway', 'OriginAccessControlOriginType': 'lambda', 'SigningBehavior': 'always', 'SigningProtocol': 'sigv4'}}},
        'SecurityHeaders': {'Type': 'AWS::CloudFront::ResponseHeadersPolicy', 'Properties': {'ResponseHeadersPolicyConfig': {
            'Name': 'vds-v2-dev-security', 'SecurityHeadersConfig': {
                'ContentTypeOptions': {'Override': True}, 'FrameOptions': {'FrameOption': 'DENY', 'Override': True},
                'ReferrerPolicy': {'ReferrerPolicy': 'no-referrer', 'Override': True},
                'StrictTransportSecurity': {'AccessControlMaxAgeSec': 31536000, 'Override': True},
                'ContentSecurityPolicy': {'Override': True, 'ContentSecurityPolicy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' https://*.amazoncognito.com https://*.amazonaws.com; img-src 'self' data: blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'; object-src 'none'"}
            }}}},
        'Distribution': {'Type': 'AWS::CloudFront::Distribution', 'Properties': {'DistributionConfig': {
            'Enabled': True, 'Comment': 'Restricted Virtual Data Scientist development workspace', 'DefaultRootObject': 'index.html',
            'PriceClass': 'PriceClass_100', 'HttpVersion': 'http2', 'ViewerCertificate': {'CloudFrontDefaultCertificate': True},
            'Origins': [
                {'Id': 'site', 'DomainName': attr('Site', 'RegionalDomainName'), 'S3OriginConfig': {'OriginAccessIdentity': ''}, 'OriginAccessControlId': ref('StaticOac')},
                {'Id': 'gateway', 'DomainName': {'Fn::Select': [2, {'Fn::Split': ['/', attr('GatewayUrl', 'FunctionUrl')]}]},
                 'CustomOriginConfig': {'OriginProtocolPolicy': 'https-only', 'OriginSSLProtocols': ['TLSv1.2'], 'OriginReadTimeout': 60}, 'OriginAccessControlId': ref('GatewayOac')}
            ],
            'DefaultCacheBehavior': {'TargetOriginId': 'site', 'ViewerProtocolPolicy': 'redirect-to-https', 'Compress': True,
                'CachePolicyId': '658327ea-f89d-4fab-a63d-7e88639e58f6', 'ResponseHeadersPolicyId': ref('SecurityHeaders')},
            'CacheBehaviors': [{'PathPattern': '/api/v2/*', 'TargetOriginId': 'gateway', 'ViewerProtocolPolicy': 'https-only',
                'AllowedMethods': ['GET', 'HEAD', 'OPTIONS', 'PUT', 'PATCH', 'POST', 'DELETE'], 'CachedMethods': ['GET', 'HEAD'],
                'CachePolicyId': '4135ea2d-6df8-44a3-9df3-4b5a84be39ad',
                'OriginRequestPolicyId': 'b689b0a8-53d0-40ab-baf2-68738e2966ac', 'ResponseHeadersPolicyId': ref('SecurityHeaders')}]
        }}},
        'SitePolicy': {'Type': 'AWS::S3::BucketPolicy', 'Properties': {'Bucket': ref('Site'), 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [
            {'Effect': 'Allow', 'Principal': {'Service': 'cloudfront.amazonaws.com'}, 'Action': 's3:GetObject', 'Resource': sub('${Site.Arn}/*'),
             'Condition': {'StringEquals': {'AWS:SourceArn': sub('arn:${AWS::Partition}:cloudfront::${AWS::AccountId}:distribution/${Distribution}')}}},
            {'Effect': 'Deny', 'Principal': '*', 'Action': 's3:*', 'Resource': [attr('Site', 'Arn'), sub('${Site.Arn}/*')], 'Condition': {'Bool': {'aws:SecureTransport': 'false'}}}
        ]}}},
        'AllowCloudFrontUrl': {'Type': 'AWS::Lambda::Permission', 'Properties': {
            'FunctionName': ref('Gateway'), 'Action': 'lambda:InvokeFunctionUrl', 'Principal': 'cloudfront.amazonaws.com',
            'SourceArn': sub('arn:${AWS::Partition}:cloudfront::${AWS::AccountId}:distribution/${Distribution}'), 'FunctionUrlAuthType': 'AWS_IAM'}},
        'AllowCloudFrontInvoke': {'Type': 'AWS::Lambda::Permission', 'Properties': {
            'FunctionName': ref('Gateway'), 'Action': 'lambda:InvokeFunction', 'Principal': 'cloudfront.amazonaws.com',
            'SourceArn': sub('arn:${AWS::Partition}:cloudfront::${AWS::AccountId}:distribution/${Distribution}'), 'InvokedViaFunctionUrl': True}}
    }
    stream_resources={
        'StreamLogs':{'Type':'AWS::Logs::LogGroup','Properties':{'LogGroupName':'/aws/lambda/vds-v2-dev-stream','RetentionInDays':7}},
        'StreamRole':{'Type':'AWS::IAM::Role','Properties':{
            'AssumeRolePolicyDocument':{'Version':'2012-10-17','Statement':[{'Effect':'Allow','Principal':{'Service':'lambda.amazonaws.com'},'Action':'sts:AssumeRole'}]},
            'Policies':[{'PolicyName':'ReadVerifiedStream','PolicyDocument':{'Version':'2012-10-17','Statement':[
                {'Effect':'Allow','Action':['dynamodb:GetItem','dynamodb:DeleteItem'],'Resource':sub('arn:${AWS::Partition}:dynamodb:${AWS::Region}:${AWS::AccountId}:table/${StateTable}')},
                {'Effect':'Allow','Action':['s3:GetObject'],'Resource':sub('arn:${AWS::Partition}:s3:::${DataBucket}/*/*/runs/*.json')},
                {'Effect':'Allow','Action':['transcribe:StartStreamTranscription'],'Resource':'*'},
                {'Effect':'Allow','Action':['logs:CreateLogStream','logs:PutLogEvents'],'Resource':sub('arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/vds-v2-dev-stream:*')}
            ]}}]}},
        'Stream':{'Type':'AWS::Lambda::Function','DependsOn':'StreamLogs','Properties':{
            'FunctionName':'vds-v2-dev-stream','Runtime':'nodejs22.x','Architectures':['arm64'],'Handler':'index.handler',
            'Role':attr('StreamRole','Arn'),'Code':{'S3Bucket':ref('DataBucket'),'S3Key':ref('StreamCodeKey')},'Timeout':35,'MemorySize':128,
            'Environment':{'Variables':{'VDS_STATE_TABLE':ref('StateTable'),'VDS_DATA_BUCKET':ref('DataBucket')}}}},
        'StreamUrl':{'Type':'AWS::Lambda::Url','Properties':{'TargetFunctionArn':ref('Stream'),'AuthType':'AWS_IAM','InvokeMode':'RESPONSE_STREAM'}},
        'AllowCloudFrontStreamUrl':{'Type':'AWS::Lambda::Permission','Properties':{'FunctionName':ref('Stream'),'Action':'lambda:InvokeFunctionUrl','Principal':'cloudfront.amazonaws.com',
            'SourceArn':sub('arn:${AWS::Partition}:cloudfront::${AWS::AccountId}:distribution/${Distribution}'),'FunctionUrlAuthType':'AWS_IAM'}},
        'AllowCloudFrontStreamInvoke':{'Type':'AWS::Lambda::Permission','Properties':{'FunctionName':ref('Stream'),'Action':'lambda:InvokeFunction','Principal':'cloudfront.amazonaws.com',
            'SourceArn':sub('arn:${AWS::Partition}:cloudfront::${AWS::AccountId}:distribution/${Distribution}'),'InvokedViaFunctionUrl':True}}
    }
    for resource in stream_resources.values():resource['Condition']='HasStreaming'
    resources.update(stream_resources)
    resources['Gateway']['Properties']['Environment']['Variables'].update({
        'VDS_STREAMING_ENABLED':{'Fn::If':['HasStreaming','true','false']},'VDS_STATE_TABLE':ref('StateTable'),
        'VDS_GUEST_ENABLED':ref('GuestEnabled'),'VDS_APP_ORIGIN':ref('AppOrigin'),'VDS_LEGACY_ORIGIN':ref('LegacyOrigin')})
    distribution=resources['Distribution']['Properties']['DistributionConfig']
    distribution['Aliases']={'Fn::If':['HasDomain',[ref('CustomDomain')],ref('AWS::NoValue')]}
    distribution['ViewerCertificate']={'Fn::If':['HasDomain',{'AcmCertificateArn':ref('CertificateArn'),'SslSupportMethod':'sni-only','MinimumProtocolVersion':'TLSv1.2_2021'},{'CloudFrontDefaultCertificate':True}]}
    distribution['Origins'].append({'Fn::If':['HasStreaming',{
        'Id':'stream','DomainName':{'Fn::Select':[2,{'Fn::Split':['/',attr('StreamUrl','FunctionUrl')]}]},
        'CustomOriginConfig':{'OriginProtocolPolicy':'https-only','OriginSSLProtocols':['TLSv1.2'],'OriginReadTimeout':35},'OriginAccessControlId':ref('GatewayOac')},ref('AWS::NoValue')]})
    distribution['CacheBehaviors'].insert(0,{'Fn::If':['HasStreaming',{
        'PathPattern':'/api/v2/events/stream','TargetOriginId':'stream','ViewerProtocolPolicy':'https-only',
        'AllowedMethods':['GET','HEAD','OPTIONS','PUT','PATCH','POST','DELETE'],'CachedMethods':['GET','HEAD'],
        'CachePolicyId':'4135ea2d-6df8-44a3-9df3-4b5a84be39ad','OriginRequestPolicyId':'b689b0a8-53d0-40ab-baf2-68738e2966ac',
        'ResponseHeadersPolicyId':ref('SecurityHeaders')},ref('AWS::NoValue')]})
    speech_behavior=json.loads(json.dumps(distribution['CacheBehaviors'][0]))
    speech_behavior['Fn::If'][1]['PathPattern']='/api/v2/speech/transcribe'
    distribution['CacheBehaviors'].insert(0,speech_behavior)
    return {'AWSTemplateFormatVersion': '2010-09-09', 'Description': 'Restricted VDS development web access; existing public site unchanged',
        'Parameters': {'RuntimeArn': {'Type': 'String'}, 'DataBucket': {'Type': 'String'}, 'CodeKey': {'Type': 'String'},
                       'AppOrigin': {'Type': 'String', 'Default': 'https://localhost'}, 'StateTable':{'Type':'String','Default':''},
                       'CustomDomain':{'Type':'String','Default':''},'CertificateArn':{'Type':'String','Default':''},
                       'LegacyOrigin':{'Type':'String','Default':'https://d19bkp3wlr8r7k.cloudfront.net'},
                       'StreamCodeKey':{'Type':'String','Default':''},'PreviewEnabled':{'Type':'String','Default':'false','AllowedValues':['false','true']},'GuestEnabled':{'Type':'String','Default':'false','AllowedValues':['false','true']}},
        'Conditions':{'HasStreaming':{'Fn::Not':[{'Fn::Equals':[ref('StreamCodeKey'),'']}]},
            'HasPreview':{'Fn::Equals':[ref('PreviewEnabled'),'true']},'HasGuests':{'Fn::Equals':[ref('GuestEnabled'),'true']},'HasDomain':{'Fn::Not':[{'Fn::Equals':[ref('CustomDomain'),'']}]}},'Resources': resources,
        'Outputs': {'SiteBucket': {'Value': ref('Site')}, 'WebUrl': {'Value': {'Fn::If':['HasDomain',sub('https://${CustomDomain}'),sub('https://${Distribution.DomainName}')]}},
                    'LegacyWebUrl':{'Value':sub('https://${Distribution.DomainName}')},
                    'DistributionId': {'Value': ref('Distribution')}, 'UserPoolId': {'Value': ref('Users')},
                    'ClientId': {'Value': ref('Client')}, 'LoginDomain': {'Value': sub('https://${LoginDomain}.auth.${AWS::Region}.amazoncognito.com')},
                    'GatewayOriginUrl': {'Value': attr('GatewayUrl', 'FunctionUrl')},
                    'PreviewEnabled':{'Value':ref('PreviewEnabled')},'GuestEnabled':{'Value':ref('GuestEnabled')},
                    'StreamOriginUrl':{'Condition':'HasStreaming','Value':attr('StreamUrl','FunctionUrl')}}}


if __name__ == '__main__':
    result = template()
    assert result['Resources']['GatewayUrl']['Properties']['AuthType'] == 'AWS_IAM'
    assert result['Parameters']['GuestEnabled']['Default']=='false'
    Path('aws_backend/cloud-dev/web-template.json').write_text(json.dumps(result, indent=2) + '\n')
