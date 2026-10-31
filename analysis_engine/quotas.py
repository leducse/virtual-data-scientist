"""Transactional trial reservations; telemetry is never the source of quota truth."""
from __future__ import annotations

import json
import os
import time
from boto3.dynamodb.types import TypeSerializer
from analysis_engine.ingestion import InputError

RESERVE_TOKENS = 50000
_serializer=TypeSerializer()


def encoded(values):
    return {key:_serializer.serialize(value) for key,value in values.items()}


class Quotas:
    def __init__(self,table):
        self.table=table
        # Table.meta.client has resource transformations; use a fresh low-level
        # client from the same authenticated session only for wire transactions.
        import boto3
        from botocore.config import Config
        self.client=boto3.client('dynamodb',region_name=table.meta.client.meta.region_name,
            config=Config(connect_timeout=5,read_timeout=10,retries={'total_max_attempts':1}))

    def reserve(self,owner,run,principal):
        quota_owner=principal['owner']
        limit=5 if principal['kind']=='guest' else 20
        token_limit=250000 if principal['kind']=='guest' else 1000000
        item={'pk':owner,'sk':'run#'+run['id'],'doc':json.dumps(run,allow_nan=False),
              'state':run['status'],'version':0,'expires_at':int(time.time())+7*86400}
        reservation={'pk':'quota#'+quota_owner,'sk':'reservation#'+run['id'],'state':'reserved',
                     'tokens':RESERVE_TOKENS,'expires_at':int(time.time())+7*86400}
        actions=[
            {'Put':{'TableName':self.table.name,'Item':encoded(item),'ConditionExpression':'attribute_not_exists(pk)'}},
            {'Put':{'TableName':self.table.name,'Item':encoded(reservation),'ConditionExpression':'attribute_not_exists(pk)'}},
            {'Update':{'TableName':self.table.name,'Key':encoded({'pk':'quota#'+quota_owner,'sk':'allowance'}),
                'UpdateExpression':'ADD credits :one, tokens_committed :tokens',
                'ConditionExpression':'(attribute_not_exists(credits) OR credits < :limit) AND (attribute_not_exists(tokens_committed) OR tokens_committed <= :available)',
                'ExpressionAttributeValues':encoded({':one':1,':tokens':RESERVE_TOKENS,':limit':limit,':available':token_limit-RESERVE_TOKENS})}},
            {'Update':{'TableName':self.table.name,'Key':encoded({'pk':'capacity','sk':'development-admissions-v2'}),
                'UpdateExpression':'ADD admissions :one','ConditionExpression':'attribute_not_exists(admissions) OR admissions < :limit',
                'ExpressionAttributeValues':encoded({':one':1,':limit':int(os.environ.get('VDS_ADMISSION_LIMIT','20'))})}}
        ]
        try:self.client.transact_write_items(TransactItems=actions)
        except self.client.exceptions.TransactionCanceledException as exc:
            existing=self.table.get_item(Key={'pk':owner,'sk':'run#'+run['id']},ConsistentRead=True).get('Item')
            if existing:return False
            raise InputError('The analysis allowance or development-wide resource limit has been reached. Sign in for an account allowance, or contact the workspace operator.', 'quota_exceeded') from exc
        return True

    def settle(self,principal,run_id,usage,succeeded,unknown=False):
        actual=sum(max(0,int(item.get('usage',{}).get('inputTokens',0)))+max(0,int(item.get('usage',{}).get('outputTokens',0))) for item in usage)
        held=RESERVE_TOKENS if unknown else actual
        try:
            self.client.transact_write_items(TransactItems=[
                {'Update':{'TableName':self.table.name,'Key':encoded({'pk':'quota#'+principal['owner'],'sk':'reservation#'+run_id}),
                    'UpdateExpression':'SET #state = :settled, actual_tokens = :actual, unknown_usage = :unknown',
                    'ConditionExpression':'#state = :reserved','ExpressionAttributeNames':{'#state':'state'},
                    'ExpressionAttributeValues':encoded({':settled':'settled',':reserved':'reserved',':actual':actual,':unknown':unknown})}},
                {'Update':{'TableName':self.table.name,'Key':encoded({'pk':'quota#'+principal['owner'],'sk':'allowance'}),
                    'UpdateExpression':'ADD credits :credit_delta, tokens_committed :token_delta, measured_tokens :actual',
                    'ExpressionAttributeValues':encoded({':credit_delta':0 if succeeded or unknown else -1,':token_delta':held-RESERVE_TOKENS,':actual':actual})}}
            ])
        except self.client.exceptions.TransactionCanceledException:
            # A repeated finalizer cannot refund or debit a second time.
            row=self.table.get_item(Key={'pk':'quota#'+principal['owner'],'sk':'reservation#'+run_id},ConsistentRead=True).get('Item')
            if not row or row.get('state')!='settled':raise

    def status(self,principal):
        row=self.table.get_item(Key={'pk':'quota#'+principal['owner'],'sk':'allowance'},ConsistentRead=True).get('Item',{})
        limit=5 if principal['kind']=='guest' else 20
        return {'kind':principal['kind'],'limit':limit,'remaining':max(0,limit-int(row.get('credits',0))),
                'tokens_measured':int(row.get('measured_tokens',0)), 'note':'Additional token, compute and development-wide limits apply.'}
