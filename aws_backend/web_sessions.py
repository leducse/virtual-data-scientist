"""Server-issued guest sessions and atomic claims into verified account namespaces."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from http.cookies import SimpleCookie

import boto3
from boto3.dynamodb.types import TypeSerializer
from botocore.config import Config

COOKIE='__Host-vds-guest'
_serializer=TypeSerializer()
wire=lambda values:{k:_serializer.serialize(v) for k,v in values.items()}


class SessionError(ValueError):
    def __init__(self,message,code='unauthenticated',status=401):
        super().__init__(message);self.code,self.status=code,status


class Sessions:
    def __init__(self,table):
        self.table=table
        self.client=boto3.client('dynamodb',region_name=table.meta.client.meta.region_name,
            config=Config(connect_timeout=5,read_timeout=10,retries={'total_max_attempts':1}))

    def cookie(self,event):
        cookies=SimpleCookie()
        try:cookies.load('; '.join(event.get('cookies') or []) or (event.get('headers') or {}).get('cookie',''))
        except Exception:return None
        token=cookies.get(COOKIE)
        if not token or not re.fullmatch(r'[a-f0-9]{64}',token.value):return None
        return hashlib.sha256(token.value.encode()).hexdigest()

    def get(self,pk,sk):
        return self.table.get_item(Key={'pk':pk,'sk':sk},ConsistentRead=True).get('Item')

    def guest(self,event,allow_claimed=False):
        key=self.cookie(event)
        row=self.get('guest#'+key,'session') if key else None
        if not row or int(row['expires_at'])<int(time.time()) or (row.get('claimed_by') and not allow_claimed):
            raise SessionError('Sign in to continue with this workspace.')
        return row

    def start(self,event):
        key=self.cookie(event)
        existing=self.get('guest#'+key,'session') if key else None
        if existing and existing.get('claimed_by'):
            raise SessionError('Sign in to restore the projects connected to your account.')
        try:self.guest(event);return {'ok':True,'guest':True}
        except SessionError:pass
        token=secrets.token_hex(32);owner=hashlib.sha256(token.encode()).hexdigest()
        now=int(time.time());day=now//86400
        ip=event.get('requestContext',{}).get('http',{}).get('sourceIp','unknown')
        ip_hash=hashlib.sha256(ip.encode()).hexdigest()
        actions=[]
        for pk,limit in [('edge#guest#'+ip_hash,2),('edge#guest#global',20)]:
            actions.append({'Update':{'TableName':self.table.name,'Key':wire({'pk':pk,'sk':str(day)}),
                'UpdateExpression':'SET expires_at = :expiry ADD sessions :one',
                'ConditionExpression':'attribute_not_exists(sessions) OR sessions < :limit',
                'ExpressionAttributeValues':wire({':expiry':now+7*86400,':one':1,':limit':limit})}})
        actions.append({'Put':{'TableName':self.table.name,'Item':wire({'pk':'guest#'+owner,'sk':'session','owner':owner,'expires_at':now+7*86400}),'ConditionExpression':'attribute_not_exists(pk)'}})
        try:self.client.transact_write_items(TransactItems=actions)
        except self.client.exceptions.TransactionCanceledException as exc:
            raise SessionError('The development guest allowance is currently full. Sign in with an invited account.','capacity_exceeded',429) from exc
        return {'ok':True,'guest':True,'_cookies':[f'{COOKIE}={token}; Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800']}

    def owners(self,account):
        row=self.get('identity#'+account,'workspaces') or {}
        return [account,*row.get('namespaces',[])]

    def claim(self,account,event):
        try:guest=self.guest(event,allow_claimed=True)
        except SessionError:return {'ok':True,'claimed':False}
        owner=guest['owner']
        if owner in self.owners(account):return {'ok':True,'claimed':False}
        if guest.get('claimed_by') and guest['claimed_by']!=account:
            raise SessionError('This trial workspace already belongs to another account.','access_denied',403)
        try:
            self.client.transact_write_items(TransactItems=[
                {'Update':{'TableName':self.table.name,'Key':wire({'pk':guest['pk'],'sk':'session'}),
                    'UpdateExpression':'SET claimed_by = :account',
                    'ConditionExpression':'attribute_exists(pk) AND (attribute_not_exists(claimed_by) OR claimed_by = :account)',
                    'ExpressionAttributeValues':wire({':account':account})}},
                {'Update':{'TableName':self.table.name,'Key':wire({'pk':'identity#'+account,'sk':'workspaces'}),
                    'UpdateExpression':'SET namespaces = list_append(if_not_exists(namespaces, :empty), :next)',
                    'ConditionExpression':'attribute_not_exists(namespaces) OR (NOT contains(namespaces, :owner) AND size(namespaces) < :limit)',
                    'ExpressionAttributeValues':wire({':empty':[],':next':[owner],':owner':owner,':limit':3})}}
            ])
        except self.client.exceptions.TransactionCanceledException as exc:
            if owner not in self.owners(account):raise SessionError('Workspace claim could not complete. Your trial data remains saved.','state_conflict',409) from exc
        return {'ok':True,'claimed':True}

    def locate(self,owners,kind,record_id):
        for owner in owners:
            row=self.get(owner,kind+'#'+str(record_id))
            if row:
                doc=json.loads(row['doc'])
                if kind=='upload' and doc.get('incoming'):return owner
                dataset=doc if kind=='dataset' else json.loads((self.get(owner,'dataset#'+doc['dataset_id']) or {}).get('doc','{}'))
                if dataset and not dataset.get('deleted'):return owner
        raise SessionError('The requested data or analysis is not available.','not_found',404)

    def rate(self,owner,method):
        minute=int(time.time())//60
        limit=120 if method=='GET' else 20
        try:
            self.table.update_item(Key={'pk':'edge#request#'+owner,'sk':f'{minute}:{method}'},
                UpdateExpression='SET expires_at = :expiry ADD requests :one',
                ConditionExpression='attribute_not_exists(requests) OR requests < :limit',
                ExpressionAttributeValues={':expiry':int(time.time())+3600,':one':1,':limit':limit})
        except self.table.meta.client.exceptions.ConditionalCheckFailedException as exc:
            raise SessionError('Please wait a moment before making another request.','capacity_exceeded',429) from exc
