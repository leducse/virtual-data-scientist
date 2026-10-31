import json
import time
import unittest
import os
import io
from unittest.mock import Mock,patch
from concurrent.futures import ThreadPoolExecutor

import boto3
from moto import mock_aws

from analysis_engine.ingestion import InputError
from analysis_engine.quotas import Quotas
from aws_backend.web_sessions import Sessions,SessionError
from aws_backend.web_gateway import Gateway,RequestError


@mock_aws
class TrialTests(unittest.TestCase):
    def setUp(self):
        self.table=boto3.resource('dynamodb',region_name='us-east-1').create_table(TableName='trial',
            KeySchema=[{'AttributeName':'pk','KeyType':'HASH'},{'AttributeName':'sk','KeyType':'RANGE'}],
            AttributeDefinitions=[{'AttributeName':'pk','AttributeType':'S'},{'AttributeName':'sk','AttributeType':'S'}],BillingMode='PAY_PER_REQUEST')
        self.sessions=Sessions(self.table)
        self.quota=Quotas(self.table)
        self.principal={'owner':'a'*64,'kind':'guest'}

    def run_doc(self,index):
        return {'id':f'{index:032x}','dataset_id':'d'*32,'status':'queued','version_counter':0}

    def test_five_analyses_reserve_once_and_unknown_usage_is_retained(self):
        owner=self.principal['owner']
        for index in range(5):
            run=self.run_doc(index)
            self.assertTrue(self.quota.reserve(owner,run,self.principal))
            self.assertFalse(self.quota.reserve(owner,run,self.principal))
            self.quota.settle(self.principal,run['id'],[{'usage':{'inputTokens':100,'outputTokens':20}}],True)
            self.quota.settle(self.principal,run['id'],[],True)
        self.assertEqual(self.quota.status(self.principal)['remaining'],0)
        with self.assertRaises(InputError):self.quota.reserve(owner,self.run_doc(6),self.principal)
        self.assertEqual(self.quota.status(self.principal)['tokens_measured'],600)

    def test_confirmed_failure_refunds_credit_but_not_global_admission(self):
        run=self.run_doc(0);owner=self.principal['owner']
        self.quota.reserve(owner,run,self.principal)
        self.quota.settle(self.principal,run['id'],[],False)
        self.assertEqual(self.quota.status(self.principal)['remaining'],5)
        self.assertEqual(self.table.get_item(Key={'pk':'capacity','sk':'development-admissions-v2'})['Item']['admissions'],1)
        run=self.run_doc(1);self.quota.reserve(owner,run,self.principal)
        self.quota.settle(self.principal,run['id'],[],False,unknown=True)
        self.assertEqual(self.quota.status(self.principal)['remaining'],4)

    def test_cookie_claim_is_atomic_preserves_namespaces_and_blocks_other_account(self):
        event={'requestContext':{'http':{'sourceIp':'192.0.2.4'}},'headers':{}}
        response=self.sessions.start(event)
        event['cookies']=[response['_cookies'][0].split(';')[0]]
        owner=self.sessions.guest(event)['owner']
        self.assertTrue(self.sessions.claim('b'*64,event)['claimed'])
        self.assertEqual(self.sessions.owners('b'*64),['b'*64,owner])
        self.assertFalse(self.sessions.claim('b'*64,event)['claimed'])
        with self.assertRaises(SessionError):self.sessions.claim('c'*64,event)
        with self.assertRaises(SessionError):self.sessions.guest(event)
        with self.assertRaises(SessionError):self.sessions.start(event)

    def test_guest_reset_limit_and_resource_ownership(self):
        event={'requestContext':{'http':{'sourceIp':'192.0.2.5'}},'headers':{}}
        self.sessions.start(event);self.sessions.start(event)
        with self.assertRaises(SessionError):self.sessions.start(event)
        self.table.put_item(Item={'pk':'a'*64,'sk':'dataset#'+'d'*32,'doc':json.dumps({'id':'d'*32})})
        self.assertEqual(self.sessions.locate(['a'*64],'dataset','d'*32),'a'*64)
        with self.assertRaises(SessionError):self.sessions.locate(['b'*64],'dataset','d'*32)

    def test_gateway_account_view_keeps_its_own_and_claimed_trial_datasets(self):
        event={'requestContext':{'http':{'sourceIp':'192.0.2.6'}},'headers':{}}
        response=self.sessions.start(event);event['cookies']=[response['_cookies'][0].split(';')[0]]
        guest=self.sessions.guest(event)['owner'];account='b'*64
        self.sessions.claim(account,event)
        runtime=Mock()
        def invoke(**kwargs):
            request=json.loads(kwargs['payload'])
            self.assertEqual(request['principal'],{'owner':account,'kind':'member'})
            return {'response':io.BytesIO(json.dumps({'ok':True,'datasets':[{'id':request['owner'],'created_at':1}], 'runs':[]}).encode())}
        runtime.invoke_agent_runtime.side_effect=invoke
        with patch.dict(os.environ,{'VDS_RUNTIME_ARN':'arn:test','VDS_DATA_BUCKET':'test','VDS_APP_ORIGIN':'https://app.test','VDS_GUEST_ENABLED':'true'}):
            identity=Mock();identity.owner.return_value=account
            gateway=Gateway(identity,runtime,Mock());gateway.sessions=self.sessions
            result=gateway.route({'requestContext':{'http':{'method':'GET'}},'rawPath':'/api/v2/workspace','headers':{'x-vds-token':'test-token'}})
            self.assertEqual({d['id'] for d in result['datasets']},{guest,account})
            with self.assertRaises(RequestError):
                gateway.route({'requestContext':{'http':{'method':'POST'}},'rawPath':'/api/v2/session','headers':{'content-type':'application/json','origin':'https://evil.test'},'body':'{}'})


if __name__=='__main__':unittest.main()
