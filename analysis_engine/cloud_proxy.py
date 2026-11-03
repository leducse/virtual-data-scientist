"""Authenticated developer bridge: UI actions invoke the hosted AgentCore runtime."""
from __future__ import annotations
import base64
import json
import uuid
import boto3
from botocore.config import Config
from analysis_engine.ingestion import InputError


class CloudProxy:
    def __init__(self,arn,region):
        self.arn=arn
        self.session_id=str(uuid.uuid4())
        self.client=boto3.client('bedrock-agentcore',region_name=region,
            config=Config(connect_timeout=5,read_timeout=150,retries={'total_max_attempts':1}))

    def call(self,owner,action,payload=None):
        response=self.client.invoke_agent_runtime(agentRuntimeArn=self.arn,runtimeSessionId=self.session_id,
            payload=json.dumps({'owner':owner,'action':action,'payload':payload or {}}).encode(),qualifier='DEFAULT')
        with response['response'] as stream:
            data=json.loads(stream.read())
        if not data.get('ok'):
            error=data.get('error',{})
            raise InputError(error.get('message','The hosted analysis could not finish.'),error.get('code','dependency_failure'),error.get('details'))
        return data

    def load_sample(self,owner,sample_id):return self.call(owner,'load_sample',{'sample_id':sample_id})['dataset']
    def list(self,owner):return self.call(owner,'workspace')
    def ingest(self,owner,name,raw,sheet=None,header_row=None,question=None):
        return self.call(owner,'upload',{'name':name,'content_base64':base64.b64encode(raw).decode(),'question':question})['dataset']
    def submit(self,owner,payload):
        return self.call(owner,'submit',{key:payload[key] for key in ['dataset_id','request_key','question']})['run']
    def run(self,owner,run_id):return self.call(owner,'run',{'run_id':run_id})['run']
    def artifacts(self,owner,run_id,palette='decision'):return self.call(owner,'artifacts',{'run_id':run_id,'palette':palette})
    def prepared_data(self,owner,run_id):return self.call(owner,'prepared_data',{'run_id':run_id})
    def cancel(self,owner,run_id):return self.call(owner,'cancel',{'run_id':run_id})['run']
    def delete(self,owner,dataset_id):return self.call(owner,'delete',{'dataset_id':dataset_id})
