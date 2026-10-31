"""Live private trial acceptance against AWS; never opens anonymous production access."""
import argparse
import base64
import hashlib
import io
import json
import secrets
import threading
import time
import uuid
import zipfile
from pathlib import Path

import boto3
import requests
from botocore.config import Config


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if not args.execute:
        print('Review only: temporary IAM-only Lambda with guest policy enabled, two no-invite users, five guest summaries, quota rejection, atomic login claim and one member summary. Also probe SSE replay/download ownership. All data is synthetic; delete temporary users/function/data; retain admission accounting.');return
    session=boto3.Session(region_name='us-east-1')
    cfg=Config(connect_timeout=5,read_timeout=90,retries={'total_max_attempts':1})
    assert session.client('sts',config=cfg).get_caller_identity()['Account']=='441383083571'
    cf=session.client('cloudformation',config=cfg)
    core=cf.describe_stacks(StackName='VirtualDataScientistV2Dev')['Stacks'][0]
    web=cf.describe_stacks(StackName='VirtualDataScientistV2DevWeb')['Stacks'][0]
    assert core['StackStatus']=='UPDATE_COMPLETE' and web['StackStatus']=='UPDATE_COMPLETE'
    outputs={o['OutputKey']:o['OutputValue'] for o in web['Outputs']};params={p['ParameterKey']:p['ParameterValue'] for p in web['Parameters']}
    core_out={o['OutputKey']:o['OutputValue'] for o in core['Outputs']}
    table=session.resource('dynamodb',config=cfg).Table(core_out['StateTable'])
    functions=session.client('lambda',config=cfg);cognito=session.client('cognito-idp',config=cfg)
    runtime=session.client('bedrock-agentcore',config=cfg)
    current=functions.get_function_configuration(FunctionName='vds-v2-dev-web')
    env={k:v for k,v in current['Environment']['Variables'].items() if k in {'VDS_ISSUER','VDS_CLIENT_ID','VDS_RUNTIME_ARN','VDS_DATA_BUCKET','VDS_STATE_TABLE','VDS_APP_ORIGIN','VDS_LEGACY_ORIGIN','VDS_STREAMING_ENABLED'}}
    env['VDS_GUEST_ENABLED']='true'
    name='vds-v2-trial-test-'+uuid.uuid4().hex[:10]
    users=[];datasets=[];created=False;tokens=[];report=None
    origin=outputs.get('LegacyWebUrl',outputs['WebUrl'])
    test_ip='192.0.2.'+str(int(uuid.uuid4().hex[:2],16)%250+1)
    def call(method,path,body=None,token=None,cookie=None):
        headers={'content-type':'application/json','origin':origin}
        if token:headers['x-vds-token']=token
        event={'rawPath':'/api/v2/'+path,'requestContext':{'http':{'method':method,'sourceIp':test_ip}},
               'headers':headers,'body':json.dumps(body or {})}
        if cookie:event['cookies']=[cookie]
        response=functions.invoke(FunctionName=name,Payload=json.dumps(event).encode())
        with response['Payload'] as stream:envelope=json.load(stream)
        assert 'FunctionError' not in response,'Acceptance Lambda failed'
        return envelope['statusCode'],json.loads(envelope['body']),envelope.get('cookies',[])
    def upload(token=None,cookie=None):
        raw=(Path(__file__).resolve().parents[1]/'tests/fixtures/monthly_revenue.csv').read_bytes()
        status,stage,_=call('POST','uploads',{'name':'synthetic-trial.csv','size':len(raw)},token,cookie);assert status==200
        posted=requests.post(stage['post']['url'],data=stage['post']['fields'],files={'file':('synthetic-trial.csv',raw)},timeout=20)
        posted.raise_for_status()
        status,data,_=call('POST','datasets',{'name':'synthetic-trial.csv','upload_id':stage['upload_id']},token,cookie);assert status==200
        return data['dataset']
    def summarize(dataset,index,token=None,cookie=None):
        status,data,_=call('POST','runs',{'dataset_id':dataset['id'],'request_key':'live-trial-'+str(index),'question':'Show monthly revenue'},token,cookie)
        assert status==200,(status,data.get('error',{}).get('code'))
        run=data['run'];deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            status,data,_=call('GET','runs/'+run['id'],token=token,cookie=cookie);assert status==200
            run=data['run']
            if run['status'] not in ('queued','running','reviewing'):break
            time.sleep(1)
        assert run['status']=='succeeded',run.get('error',{}).get('code','not_complete')
        assert run['result']['total']==579060 and run['result']['review']['passed']
        return run
    try:
        functions.create_function(FunctionName=name,Runtime='python3.13',Architectures=['arm64'],Role=current['Role'],Handler='web_gateway.handler',
            Code={'S3Bucket':params['DataBucket'],'S3Key':params['CodeKey']},MemorySize=256,Timeout=75,Environment={'Variables':env})
        created=True;functions.get_waiter('function_active_v2').wait(FunctionName=name,WaiterConfig={'Delay':2,'MaxAttempts':45})
        status,_,cookies=call('POST','session');assert status==200 and len(cookies)==1
        cookie=cookies[0].split(';')[0];guest_owner=hashlib.sha256(cookie.split('=',1)[1].encode()).hexdigest()
        guest=upload(cookie=cookie);datasets.append((guest_owner,guest['id']))
        assert len(guest['experience']['suggestions'])==2
        # Deliberately synthetic transport state; no model call and no analysis credit.
        probe=uuid.uuid4().hex
        doc={'id':probe,'dataset_id':guest['id'],'question':'Synthetic transport probe','status':'running','created_at':time.time(),'version_counter':0,'events':[]}
        table.put_item(Item={'pk':guest_owner,'sk':'run#'+probe,'state':'running','version':0,'doc':json.dumps(doc),'expires_at':int(time.time())+3600})
        status,ticket,_=call('POST','stream-tickets',{'run_id':probe},cookie=cookie);assert status==200
        body=json.dumps({'ticket':ticket['ticket'],'after':0})
        headers={'content-type':'application/json','x-amz-content-sha256':hashlib.sha256(body.encode()).hexdigest()}
        chunks=[];timer=None
        def finish_probe():
            doc.update(status='cancelled',events=[{'id':probe+':1','sequence':1,'run_id':probe,'stage':'transport_probe','status':'completed','attempt':1,'timestamp':time.time()}])
            table.update_item(Key={'pk':guest_owner,'sk':'run#'+probe},UpdateExpression='SET doc = :doc, #state = :state',
                ExpressionAttributeNames={'#state':'state'},ExpressionAttributeValues={':doc':json.dumps(doc),':state':'cancelled'})
        with requests.post(origin+'/api/v2/events/stream',data=body,headers=headers,stream=True,timeout=35) as response:
            response.raise_for_status()
            for line in response.iter_lines(chunk_size=1):
                text=line.decode();chunks.append(text)
                if text=='event: connected' and timer is None:
                    timer=threading.Timer(1,finish_probe);timer.start()
        if timer:timer.join()
        assert timer and 'event: finished' in chunks and any('transport_probe' in c for c in chunks),'SSE did not deliver incrementally'
        with requests.post(origin+'/api/v2/events/stream',data=body,headers=headers,timeout=10) as replay:
            assert 'event: unavailable' in replay.text,'Consumed stream ticket replayed'
        table.delete_item(Key={'pk':guest_owner,'sk':'run#'+probe})
        runs=[summarize(guest,index,cookie=cookie) for index in range(5)]
        status,blocked,_=call('POST','runs',{'dataset_id':guest['id'],'request_key':'sixth','question':'Show monthly revenue'},cookie=cookie)
        assert status==429 and blocked['error']['code']=='quota_exceeded'
        for _ in range(2):
            username='vds-trial-'+uuid.uuid4().hex[:12];password='Vds!Aa7'+secrets.token_urlsafe(24)
            result=cognito.admin_create_user(UserPoolId=outputs['UserPoolId'],Username=username,MessageAction='SUPPRESS');users.append(username)
            cognito.admin_set_user_password(UserPoolId=outputs['UserPoolId'],Username=username,Password=password,Permanent=True)
            tokens.append(cognito.admin_initiate_auth(UserPoolId=outputs['UserPoolId'],ClientId=outputs['ClientId'],AuthFlow='ADMIN_USER_PASSWORD_AUTH',AuthParameters={'USERNAME':username,'PASSWORD':password})['AuthenticationResult']['AccessToken'])
            password=None
        own=upload(token=tokens[0])
        import jwt
        account=hashlib.sha256((env['VDS_ISSUER']+'\0'+jwt.decode(tokens[0],options={'verify_signature':False})['sub']).encode()).hexdigest()
        datasets.append((account,own['id']))
        status,claimed,_=call('POST','session/claim',token=tokens[0],cookie=cookie);assert status==200 and claimed['claimed']
        status,workspace,_=call('GET','workspace',token=tokens[0]);assert status==200
        assert {guest['id'],own['id']} <= {d['id'] for d in workspace['datasets']}
        assert len([r for r in workspace['runs'] if r['status']=='succeeded'])==5
        assert call('GET','runs/'+runs[0]['id'],token=tokens[1])[0]==404
        assert call('POST','session/claim',token=tokens[1],cookie=cookie)[0]==403
        member=summarize(guest,'member',token=tokens[0])
        status,artifact,_=call('GET','runs/'+member['id']+'/artifacts',token=tokens[0]);assert status==200
        exported=requests.get(artifact['url'],timeout=10);exported.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(exported.content)) as bundle:
            assert {'analysis.py','visualization.py','analysis.ipynb','plan.json','figures.json','presentation.json'} <= set(bundle.namelist())
        assert call('GET','runs/'+member['id']+'/artifacts',token=tokens[1])[0]==404
        report={'private_guest_lambda_only':True,'no_anonymous_launch':True,'guest_completed_analyses':5,'sixth_denied':True,
                'existing_and_trial_workspaces_preserved':True,'member_continued':True,'other_account_denied':True,
                'incremental_sse_and_single_use_ticket':True,'reproduction_bundle_downloaded':True,'temporary_resources_removed_on_exit':True}
    finally:
        cleanup_errors=[]
        for owner,dataset_id in datasets:
            try:
                response=runtime.invoke_agent_runtime(agentRuntimeArn=core_out['RuntimeArn'],runtimeSessionId=owner,qualifier='DEFAULT',
                    payload=json.dumps({'owner':owner,'action':'delete','payload':{'dataset_id':dataset_id}}).encode())
                with response['response'] as body:assert json.load(body)['ok']
            except Exception as exc:cleanup_errors.append(type(exc).__name__)
        for username in users:
            try:cognito.admin_delete_user(UserPoolId=outputs['UserPoolId'],Username=username)
            except Exception as exc:cleanup_errors.append(type(exc).__name__)
        tokens.clear()
        if created:
            try:functions.delete_function(FunctionName=name)
            except Exception as exc:cleanup_errors.append(type(exc).__name__)
            logs=session.client('logs',config=cfg)
            try:logs.delete_log_group(logGroupName='/aws/lambda/'+name)
            except logs.exceptions.ResourceNotFoundException:pass
            except Exception as exc:cleanup_errors.append(type(exc).__name__)
        if cleanup_errors:raise RuntimeError('Acceptance cleanup needs review for '+name+': '+','.join(cleanup_errors))
        print('Removed only the synthetic acceptance users/function/data; admission accounting retained.',flush=True)
    if report:
        path=Path(__file__).resolve().parents[1]/'docs/deployment/dev-v2-trial-acceptance.json'
        path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)


if __name__=='__main__':main()
