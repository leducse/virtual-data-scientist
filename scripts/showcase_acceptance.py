"""Bounded live AgentCore ML acceptance; temporary authentication stays in memory."""
from __future__ import annotations
import argparse
import hashlib
import json
import secrets
import threading
import time
import uuid
import zipfile
import io
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
import tempfile
import subprocess
import os
import boto3
import requests
from botocore.config import Config

CASES={
 'classification':('iris','Which measurements help distinguish iris species?'),
 'regression':('diabetes','How accurately can the progression score be predicted from the recorded measurements?'),
 'clustering':('blobs','What groups appear in the numeric measurements?'),
 'pca':('wine','Show a principal component view of the numeric measurements'),
 'anomaly_detection':('sales','Which rows have unusual combinations of numeric measurements?'),
 'forecast':('sales','Forecast monthly revenue for the next three months'),
}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--manifest',type=Path,default=Path('docs/deployment/dev-20261101-05.json'))
    parser.add_argument('--tasks',nargs='*',choices=list(CASES),default=list(CASES))
    parser.add_argument('--port',type=int,default=12993)
    parser.add_argument('--repro-python',type=Path,default=Path('/tmp/vds-showcase-reproduction-env/bin/python'))
    args=parser.parse_args()
    if not args.execute:print('Review only: at most six live jobs, two synthetic no-invite users, source/export checks and a loopback one-use browser login helper.');return
    outputs=json.loads(args.manifest.read_text())['outputs'];origin=outputs['WebUrl'];pool=outputs['UserPoolId'];client=outputs['ClientId']
    cfg=Config(connect_timeout=5,read_timeout=20,retries={'total_max_attempts':1})
    session=boto3.Session(region_name='us-east-1')
    assert session.client('sts',config=cfg).get_caller_identity()['Account']=='441383083571'
    cognito=session.client('cognito-idp',config=cfg);interpreter=session.client('bedrock-agentcore',config=cfg);s3=session.client('s3',config=cfg)
    core=session.client('cloudformation',config=cfg).describe_stacks(StackName='VirtualDataScientistV2Dev')['Stacks'][0]
    core_outputs={i['OutputKey']:i['OutputValue'] for i in core['Outputs']};parameters={i['ParameterKey']:i['ParameterValue'] for i in core['Parameters']}
    table=session.resource('dynamodb',config=cfg).Table(core_outputs['StateTable'])
    def admissions():return int(table.get_item(Key={'pk':'capacity','sk':'development-admissions-v2'},ConsistentRead=True).get('Item',{}).get('admissions',0))
    before=admissions();assert before+len(args.tasks)<=int(parameters.get('AdmissionLimit','20'))
    users=[];tokens=[];datasets=[];credentials=None;checks={};runs=[]
    evidence={'release':args.manifest.stem,'origin':origin,'admissions_before':before,'cases':runs,'checks':checks,'temporary_users_removed':False}
    def api(index,path,payload=None,expected=None):
        body=json.dumps(payload).encode() if payload is not None else None
        headers={'x-vds-token':tokens[index]}
        if body is not None:headers.update({'Content-Type':'application/json','x-amz-content-sha256':hashlib.sha256(body).hexdigest()})
        with requests.request('POST' if body is not None else 'GET',origin+'/api/v2/'+path,headers=headers,data=body,timeout=75) as response:
            data=response.json()
            if expected is not None:assert response.status_code==expected,(path,response.status_code)
            elif not response.ok:raise RuntimeError(str((path,response.status_code,data.get('error',{}))))
            return data
    def verify_browser():
        workspace=api(0,'workspace')
        successful=[r for r in workspace['runs'] if r['status']=='succeeded']
        checks['browser_job_count']=len(workspace['runs']);checks['browser_successful_jobs']=len(successful)
        for row in successful:
            run=api(0,'runs/'+row['id'])['run'];sandbox=run['result'].get('sandbox')
            if sandbox:
                state=interpreter.get_code_interpreter_session(codeInterpreterIdentifier='aws.codeinterpreter.v1',sessionId=sandbox['session_id'])['status']
                assert state=='TERMINATED',state
        return {'ok':True,'jobs':len(workspace['runs']),'successful':len(successful),'tokens_measured':workspace['allowance']['tokens_measured']}
    try:
        for _ in range(2):
            username='vds-showcase-'+uuid.uuid4().hex;password=secrets.token_urlsafe(30)+'aA1!'
            cognito.admin_create_user(UserPoolId=pool,Username=username,MessageAction='SUPPRESS');users.append(username)
            cognito.admin_set_user_password(UserPoolId=pool,Username=username,Password=password,Permanent=True)
            auth=cognito.admin_initiate_auth(UserPoolId=pool,ClientId=client,AuthFlow='ADMIN_USER_PASSWORD_AUTH',AuthParameters={'USERNAME':username,'PASSWORD':password})
            tokens.append(auth['AuthenticationResult']['AccessToken'])
            auth=None
            if credentials is None:credentials={'username':username,'password':password}
            password=None
        assert len(api(0,'public-datasets')['datasets'])>=10
        for task in args.tasks:
            sample,question=CASES[task]
            dataset=api(0,'public-datasets',{'sample_id':sample})['dataset']
            if dataset['id'] not in datasets:datasets.append(dataset['id'])
            api(1,'datasets/'+dataset['id']+'/delete',{},expected=404)
            key=uuid.uuid4().hex;run=api(0,'runs',{'dataset_id':dataset['id'],'question':question,'request_key':key})['run']
            deadline=time.monotonic()+240
            while run['status'] in {'queued','running','reviewing'} and time.monotonic()<deadline:
                time.sleep(2);run=api(0,'runs/'+run['id'])['run']
            if run['status']!='succeeded':
                failure={'task':task,'run_id':run['id'],'status':run['status'],'error':run.get('error')}
                attributes=cognito.get_user(AccessToken=tokens[0])['UserAttributes']
                subject=next(a['Value'] for a in attributes if a['Name']=='sub')
                owner=hashlib.sha256(('https://cognito-idp.us-east-1.amazonaws.com/'+pool+'\0'+subject).encode()).hexdigest()
                for stage in ('numerical_review','independent_review','execution'):
                    try:
                        with s3.get_object(Bucket=core_outputs['DataBucket'],Key=f'{owner}/{dataset["id"]}/runs/{run["id"]}/{stage}.json')['Body'] as body:
                            value=json.loads(body.read())
                        if stage=='execution':
                            value={key:value[key] for key in ('session_id','trace_id') if key in value}
                            if value.get('session_id'):
                                value['status']=interpreter.get_code_interpreter_session(codeInterpreterIdentifier='aws.codeinterpreter.v1',sessionId=value['session_id'])['status']
                        failure[stage]=value
                    except s3.exceptions.NoSuchKey:pass
                evidence.setdefault('failures',[]).append(failure)
                raise AssertionError((task,run['status'],run.get('error')))
            result=run['result'];assert result['task']==task and result['review']['passed'] and result['independent_review']['decision']=='accept'
            assert len(result['visuals'])>=3
            api(1,'runs/'+run['id'],expected=404)
            assert api(0,'runs',{'dataset_id':dataset['id'],'question':question,'request_key':key})['run']['id']==run['id']
            sandbox=result['sandbox'];state=interpreter.get_code_interpreter_session(codeInterpreterIdentifier='aws.codeinterpreter.v1',sessionId=sandbox['session_id'])['status'];assert state=='TERMINATED'
            bundle=api(0,'runs/'+run['id']+'/artifacts')['url'];prepared=api(0,'runs/'+run['id']+'/prepared-data')['url']
            with tempfile.TemporaryDirectory(prefix='vds-hosted-reproduction-') as directory:
                root=Path(directory)
                with requests.get(bundle,timeout=30) as response:response.raise_for_status();archive=zipfile.ZipFile(io.BytesIO(response.content));archive.extractall(root)
                with requests.get(prepared,timeout=30) as response:response.raise_for_status();(root/'dataset.parquet').write_bytes(response.content)
                subprocess.run(['uv','pip','install','--python',str(args.repro_python),'-r',str(root/'requirements.txt'),'--quiet'],check=True,timeout=180)
                env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','PYTHONPATH':str(root)}
                reproduction=subprocess.run([str(args.repro_python),'analysis.py'],cwd=root,env=env,capture_output=True,text=True,timeout=60)
                assert reproduction.returncode==0,('reproduction',task,reproduction.stderr[-500:])
            entry={'task':task,'run_id':run['id'],'dataset_id':dataset['id'],'selected_method':result['selected_method'],
                   'review':result['review'],'figures':len(result['visuals']),'versions':result['versions'],'python_version':result.get('python_version'),
                   'sandbox_status':state,'source_and_export_reproduced':True,'reproduction_python_version':subprocess.check_output([str(args.repro_python),'--version'],text=True).strip(),'model_usage':run.get('model_usage',[]),'timing_ms':result['timing_ms']}
            runs.append(entry);print(json.dumps({'task':task,'status':'passed','figures':entry['figures'],'reproduced':True}),flush=True)
        for sample in ('openml-61','openml-41517'):
            dataset=api(0,'public-datasets',{'sample_id':sample})['dataset'];datasets.append(dataset['id'])
            assert dataset['public_dataset']['upstream_sha256'] and dataset['profile']['teaching']['target']=='class'
        checks['reviewed_openml_imports']=True
        api(0,'public-datasets',{'sample_id':'https://untrusted.invalid/data'},expected=404)
        checks['unreviewed_import_denied']=True
        class Helper(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                nonlocal credentials
                if self.path=='/browser-login' and credentials:
                    result,credentials=credentials,None
                elif self.path=='/verify':result=verify_browser()
                elif self.path=='/finish':
                    result={'finished':True};threading.Thread(target=self.server.shutdown,daemon=True).start()
                else:self.send_error(404);return
                data=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
        server=HTTPServer(('127.0.0.1',args.port),Helper);timer=threading.Timer(900,server.shutdown);timer.daemon=True;timer.start()
        print(json.dumps({'ready':True,'origin':origin,'cases':len(runs),'helper_port':args.port,'admissions':admissions()}),flush=True)
        try:server.serve_forever()
        finally:server.server_close();timer.cancel()
    finally:
        if tokens:
            try:
                for row in api(0,'workspace')['datasets']:
                    api(0,'datasets/'+row['id']+'/delete',{})
                checks['synthetic_datasets_deleted']=True
            except Exception as exc:
                checks['synthetic_datasets_deleted']=False;print('Dataset cleanup needs reconciliation: '+type(exc).__name__,flush=True)
        cleanup_errors=[]
        removed=0
        try:
            for user in users:
                try:
                    cognito.admin_delete_user(UserPoolId=pool,Username=user)
                    removed+=1
                except cognito.exceptions.UserNotFoundException:
                    removed+=1
                except Exception as exc:
                    cleanup_errors.append({'operation':'delete_temporary_user','error_type':type(exc).__name__})
            evidence['temporary_users_removed']=removed==len(users)
            evidence['temporary_users_remaining']=len(users)-removed
            try:evidence['admissions_after']=admissions()
            except Exception as exc:
                cleanup_errors.append({'operation':'read_admissions','error_type':type(exc).__name__})
        finally:
            tokens.clear();credentials=None
            evidence['cleanup_errors']=cleanup_errors
            target=Path(__file__).resolve().parents[1]/'docs/deployment'/(args.manifest.stem+'-showcase-acceptance.json')
            target.write_text(json.dumps(evidence,indent=2)+'\n')
            print(json.dumps({'temporary_users_remaining':len(users)-removed,'acceptance_evidence_recorded':True,'cleanup_errors':len(cleanup_errors)}),flush=True)
        if cleanup_errors:raise RuntimeError('Acceptance cleanup or reconciliation needs attention; inspect recorded error types.')


if __name__=='__main__':main()
