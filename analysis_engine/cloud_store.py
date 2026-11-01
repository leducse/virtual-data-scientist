"""Owner-scoped S3 data/artifacts and conditional DynamoDB job state."""
from __future__ import annotations
import hashlib
import json
import time
import uuid
from contextlib import contextmanager
from boto3.dynamodb.conditions import Attr, Key
from analysis_engine.ingestion import InputError

ACTIVE = ['queued','running','reviewing']
LEASE_SECONDS = 420


class CloudStore:
    def __init__(self,s3,table,bucket):
        self.s3,self.table,self.bucket = s3,table,bucket

    @staticmethod
    def owner(value):
        import re
        if not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{64}',value):
            raise InputError('A trusted workspace identity is required.','access_denied')
        return value

    def put_blob(self,owner,key,data,content_type='application/json'):
        self.s3.put_object(Bucket=self.bucket,Key=f'{self.owner(owner)}/{key}',Body=data,ContentType=content_type,ServerSideEncryption='AES256')

    def blob(self,owner,key):
        with self.s3.get_object(Bucket=self.bucket,Key=f'{self.owner(owner)}/{key}')['Body'] as body:
            return body.read()

    def put(self,owner,kind,record_id,doc,create=False,condition=None):
        item={'pk':self.owner(owner),'sk':f'{kind}#{record_id}','doc':json.dumps(doc,allow_nan=False),'state':doc.get('status','ready'),
              'version':doc.get('version_counter',0),'expires_at':int(time.time())+7*86400}
        options = {'ConditionExpression':Attr('pk').not_exists()} if create else {'ConditionExpression':condition} if condition is not None else {}
        self.table.put_item(Item=item,**options)

    def get(self,owner,kind,record_id):
        row = self.table.get_item(Key={'pk':self.owner(owner),'sk':f'{kind}#{record_id}'},ConsistentRead=True).get('Item')
        if not row:
            raise InputError('The requested data or analysis is not available.','not_found')
        return json.loads(row['doc'])

    def dataset(self,owner,record_id):
        doc=self.get(owner,'dataset',record_id)
        if doc.get('deleted'):
            raise InputError('Dataset not found.','not_found')
        return doc

    def items(self,owner,kind):
        options={'KeyConditionExpression':Key('pk').eq(self.owner(owner)) & Key('sk').begins_with(kind+'#'),'Limit':100,'ConsistentRead':True}
        documents=[]
        while True:
            response=self.table.query(**options)
            documents.extend(json.loads(i['doc']) for i in response['Items'])
            if not response.get('LastEvaluatedKey'):return documents
            options['ExclusiveStartKey']=response['LastEvaluatedKey']

    @contextmanager
    def upload_slot(self,owner):
        key={'pk':self.owner(owner),'sk':'lease#upload'}
        token=uuid.uuid4().hex
        now=int(time.time())
        try:
            self.table.put_item(Item={**key,'token':token,'expires_at':now+LEASE_SECONDS},
                ConditionExpression=Attr('pk').not_exists() | Attr('expires_at').lt(now))
        except self.table.meta.client.exceptions.ConditionalCheckFailedException as exc:
            raise InputError('An upload is still being prepared. Retry in a moment.','capacity_exceeded') from exc
        try:yield
        finally:
            try:self.table.delete_item(Key=key,ConditionExpression=Attr('token').eq(token))
            except self.table.meta.client.exceptions.ConditionalCheckFailedException:pass

    def update_run(self,owner,run_id,**changes):
        for _ in range(3):
            run=self.get(owner,'run',run_id)
            if run['status'] not in ACTIVE:
                return False
            version=run.get('version_counter',0)
            run.update(changes,updated_at=time.time(),version_counter=version+1)
            try:
                self.put(owner,'run',run_id,run,condition=Attr('version').eq(version) & Attr('state').is_in(ACTIVE))
                return True
            except self.table.meta.client.exceptions.ConditionalCheckFailedException:
                continue
        raise InputError('Analysis state changed concurrently; reconnect to see its current status.','state_conflict')

    def event(self, owner, run_id, stage, status, attempt=1, duration_ms=None):
        from analysis_engine.telemetry import emit
        for _ in range(5):
            run = self.get(owner, 'run', run_id)
            version = run.get('version_counter', 0)
            events = run.setdefault('events', [])
            previous=next((e for e in events if (e['stage'],e['status'],e['attempt'])==(stage,status,attempt)),None)
            if previous:return previous
            if len(events) >= 80:
                raise InputError('Analysis event limit reached.', 'output_limit')
            event = {'sequence': len(events) + 1, 'id': f'{run_id}:{len(events)+1}',
                     'run_id': run_id, 'stage': stage, 'status': status, 'attempt': attempt, 'timestamp': time.time()}
            if duration_ms is not None:
                event['duration_ms'] = round(duration_ms, 2)
            events.append(event)
            run['version_counter'] = version + 1
            try:
                self.put(owner, 'run', run_id, run, condition=Attr('version').eq(version))
                emit(event='workflow_stage', **{k: v for k, v in event.items() if k not in {'id', 'timestamp'}})
                return event
            except self.table.meta.client.exceptions.ConditionalCheckFailedException:
                continue
        raise InputError('Analysis event state changed concurrently.', 'state_conflict')

    def acquire(self,owner,run_id):
        now=int(time.time())
        claimed=[]
        def claim(partition,slot):
            self.table.put_item(Item={'pk':partition,'sk':slot,'run_id':run_id,'expires_at':now+LEASE_SECONDS},
                                ConditionExpression=Attr('pk').not_exists() | Attr('expires_at').lt(now))
            claimed.append((partition,slot))
        try:
            claim(owner,'lease#deep')
            for slot in ['lease#global1','lease#global2']:
                try:
                    claim('capacity',slot)
                    return claimed
                except self.table.meta.client.exceptions.ConditionalCheckFailedException:
                    pass
            raise InputError('Both deep-analysis slots are occupied. Please retry after an analysis finishes.','capacity_exceeded')
        except self.table.meta.client.exceptions.ConditionalCheckFailedException as exc:
            self.release(claimed,run_id)
            raise InputError('This workspace already has an active analysis.','capacity_exceeded') from exc
        except Exception:
            self.release(claimed,run_id)
            raise

    def release(self,claims,run_id):
        for pk,sk in claims:
            try:
                self.table.delete_item(Key={'pk':pk,'sk':sk},ConditionExpression=Attr('run_id').eq(run_id))
            except self.table.meta.client.exceptions.ConditionalCheckFailedException:
                pass

    def run(self,owner,run_id):
        run=self.get(owner,'run',run_id)
        self.dataset(owner,run['dataset_id'])
        if run['status'] in ACTIVE and time.time()>run['created_at']+LEASE_SECONDS:
            self.update_run(owner,run_id,status='interrupted',stage='Execution was interrupted. Submit a new request to retry safely.',error={'code':'worker_interrupted','message':'The execution lease expired; the operation was not duplicated.'})
            run=self.get(owner,'run',run_id)
        if run.get('result_key'):
            run['result']=json.loads(self.blob(owner,run['result_key']))
        return run

    def workspace(self,owner,compact=False):
        datasets=[d for d in self.items(owner,'dataset') if not d.get('deleted')]
        runs=[]
        remaining=2*1024*1024
        for r in sorted(self.items(owner,'run'),key=lambda r:r['created_at'],reverse=True):
            try:
                run=self.run(owner,r['id'])
                if compact and run.get('result'):
                    run['result']={k:v for k,v in run['result'].items() if k not in {'sandbox','executed_code','evidence','model_usage'}}
                    size=len(json.dumps(run['result']).encode())
                    run['result_available']=True
                    if size>remaining:run['result']=None
                    else:remaining-=size
                runs.append(run)
            except InputError as exc:
                if exc.code!='not_found':raise
        return {'datasets':sorted(datasets,key=lambda d:d['created_at'],reverse=True),'runs':runs,'mode':'agentcore_development','cloud_enabled':True}

    def delete(self,owner,dataset_id):
        self.dataset(owner,dataset_id)
        self.put(owner,'dataset',dataset_id,{'id':dataset_id,'deleted':True})
        # Revoke first; a late worker cannot publish readable evidence after this tombstone.
        for run in self.items(owner,'run'):
            if run['dataset_id']==dataset_id:
                if run['status'] in ACTIVE:
                    self.update_run(owner,run['id'],status='cancelled',stage='Dataset deleted.')
                self.table.delete_item(Key={'pk':owner,'sk':'run#'+run['id']})
        paginator=self.s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=self.bucket,Prefix=f'{owner}/{dataset_id}/'):
            objects=[{'Key':o['Key']} for o in page.get('Contents',[])]
            if objects:
                self.s3.delete_objects(Bucket=self.bucket,Delete={'Objects':objects,'Quiet':True})
        return {'deleted':True,'dataset_id':dataset_id}
