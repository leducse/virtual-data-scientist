"""Verified-user facade for the separate AgentCore development workspace.

CloudFront OAC signs Authorization for Lambda. The browser's Cognito access token
travels in x-vds-token and is never logged or used as an owner supplied by clients.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import uuid
import time

import boto3
import jwt
from botocore.config import Config
try:
    from web_sessions import Sessions, SessionError
except ImportError:
    from aws_backend.web_sessions import Sessions, SessionError

MAX_UPLOAD = 10 * 1024 * 1024
_gateway = None


class RequestError(ValueError):
    def __init__(self, message, code='invalid_input', status=400):
        super().__init__(message)
        self.code, self.status = code, status


class Identity:
    def __init__(self, issuer, client_id, keys=None):
        self.issuer, self.client_id = issuer, client_id
        self.keys = keys or jwt.PyJWKClient(issuer + '/.well-known/jwks.json', timeout=5)

    def verify(self, token):
        if not isinstance(token, str) or not 32 <= len(token) <= 16000:
            raise RequestError('Sign in to open your workspace.', 'unauthenticated', 401)
        try:
            key = self.keys.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=['RS256'], issuer=self.issuer,
                                options={'verify_aud': False, 'require': ['exp', 'iat', 'iss', 'sub', 'client_id', 'token_use']})
            if claims['token_use'] != 'access' or claims['client_id'] != self.client_id:
                raise jwt.InvalidTokenError('Wrong token purpose or client')
            # Cognito subjects are opaque identifiers, not necessarily RFC UUIDs.
            if not isinstance(claims['sub'], str) or not 1 <= len(claims['sub']) <= 256:
                raise jwt.InvalidTokenError('Invalid subject')
        except (jwt.PyJWTError, jwt.PyJWKClientError, ValueError, TypeError) as exc:
            raise RequestError('Your sign-in has expired or is invalid. Sign in again.', 'unauthenticated', 401) from exc
        return hashlib.sha256((self.issuer + '\0' + claims['sub']).encode()).hexdigest(),int(claims['exp'])

    def owner(self,token):
        return self.verify(token)[0]


class Gateway:
    def __init__(self, identity=None, runtime=None, s3=None):
        region = os.environ.get('AWS_REGION', 'us-east-1')
        cfg = Config(connect_timeout=5, read_timeout=65, retries={'total_max_attempts': 1})
        self.identity = identity or Identity(os.environ['VDS_ISSUER'], os.environ['VDS_CLIENT_ID'])
        self.runtime = runtime or boto3.client('bedrock-agentcore', region_name=region, config=cfg)
        self.s3 = s3 or boto3.client('s3', region_name=region, config=Config(signature_version='s3v4', connect_timeout=5, read_timeout=10, retries={'total_max_attempts': 1}))
        self.arn, self.bucket = os.environ['VDS_RUNTIME_ARN'], os.environ['VDS_DATA_BUCKET']
        self.sessions=Sessions(boto3.resource('dynamodb',region_name=region,config=cfg).Table(os.environ['VDS_STATE_TABLE'])) if os.environ.get('VDS_STATE_TABLE') else None
        self.principal=None

    def call(self, owner, action, payload=None):
        response = self.runtime.invoke_agent_runtime(agentRuntimeArn=self.arn,
            runtimeSessionId=owner, qualifier='DEFAULT',
            payload=json.dumps({'owner': owner, 'action': action, 'payload': payload or {},
                'principal':self.principal or {'owner':owner,'kind':'member'}}).encode())
        with response['response'] as body:
            data = json.loads(body.read())
        if not data.get('ok'):
            error = data.get('error', {})
            code = error.get('code', 'dependency_failure')
            status = {'not_found': 404, 'access_denied': 403, 'capacity_exceeded': 429,
                      'idempotency_conflict': 409, 'upload_limit': 413, 'dependency_failure': 503, 'quota_exceeded':429}.get(code, 400)
            raise RequestError(error.get('message', 'The analysis service could not complete this request.'), code, status)
        return data

    def route(self, event):
        headers = {k.lower(): v for k, v in (event.get('headers') or {}).items()}
        request = event.get('requestContext', {}).get('http', {})
        method, path = request.get('method'), event.get('rawPath', '')
        allowed_origins={os.environ.get('VDS_APP_ORIGIN'),os.environ.get('VDS_LEGACY_ORIGIN'),os.environ.get('VDS_PREVIOUS_ORIGIN')}-{None,''}
        if method=='POST' and headers.get('origin') and headers['origin'] not in allowed_origins:
            raise RequestError('This origin is not allowed.','access_denied',403)
        body = {}
        if method == 'POST':
            if headers.get('content-type', '').split(';')[0] != 'application/json':
                raise RequestError('Use application/json.')
            raw = event.get('body') or ''
            if len(raw) > 90000:
                raise RequestError('The request is too large.', 'upload_limit', 413)
            raw = base64.b64decode(raw, validate=True).decode() if event.get('isBase64Encoded') else raw
            if len(raw.encode()) > 65536:
                raise RequestError('The request is too large.', 'upload_limit', 413)
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise RequestError('JSON body must be an object.')
        if method=='POST' and path=='/api/v2/session':
            if not self.sessions or os.environ.get('VDS_GUEST_ENABLED')!='true':
                raise RequestError('Sign in to open the development workspace.','unauthenticated',401)
            if headers.get('origin') not in allowed_origins:
                raise RequestError('This origin is not allowed.','access_denied',403)
            return self.sessions.start(event)
        if self.sessions and path in ('/api/v2/auth/session','/api/v2/auth/logout'):
            if method=='POST':
                if headers.get('origin') not in allowed_origins:
                    raise RequestError('This origin is not allowed.','access_denied',403)
                if path.endswith('/logout'):return self.sessions.logout(event)
                account,expiry=self.identity.verify(headers.get('x-vds-token'))
                self.sessions.rate(account,method)
                result=self.sessions.login(account,expiry,event)
                # A shared browser may still carry another account's claimed trial cookie.
                # Signing in is independent of claiming that trial's data.
                try:self.sessions.claim(account,event)
                except SessionError as exc:
                    if exc.code!='access_denied':raise
                return result
            if method=='GET' and path.endswith('/session'):
                member=self.sessions.member(event)
                return {'ok':True,'signed_in':bool(member),**({'identity_id':member['owner'],'expires_at':int(member['expires_at'])} if member else {})}
            raise RequestError('Endpoint not found.','not_found',404)
        member=self.sessions.member(event) if self.sessions else None
        if headers.get('x-vds-token'):
            owner=self.identity.owner(headers['x-vds-token'])
            self.principal={'owner':owner,'kind':'member'}
            owners=self.sessions.owners(owner) if self.sessions else [owner]
        elif member:
            owner=member['owner'];owners=self.sessions.owners(owner)
            self.principal={'owner':owner,'kind':'member'}
            if method=='POST' and headers.get('origin') not in allowed_origins:
                raise RequestError('This origin is not allowed.','access_denied',403)
        elif self.sessions and os.environ.get('VDS_GUEST_ENABLED')=='true':
            owner=self.sessions.guest(event)['owner'];owners=[owner]
            self.principal={'owner':owner,'kind':'guest'}
            if method=='POST' and headers.get('origin') not in allowed_origins:
                raise RequestError('This origin is not allowed.','access_denied',403)
        else:
            owner=self.identity.owner(None)
            owners=[owner]
        if self.sessions:
            self.sessions.rate(self.principal['owner'],method)
            if method=='POST' and path=='/api/v2/session/claim':
                if self.principal['kind']!='member':raise RequestError('Sign in first.','unauthenticated',401)
                return self.sessions.claim(owner,event)
        if method == 'GET' and path == '/api/v2/workspace':
            result=self.call(owner, 'workspace', {'compact': True})
            for namespace in owners[1:]:
                other=self.call(namespace,'workspace',{'compact':True})
                result['datasets'].extend(other['datasets']);result['runs'].extend(other['runs'])
            result['datasets'].sort(key=lambda d:d['created_at'],reverse=True)
            result['runs'].sort(key=lambda r:r['created_at'],reverse=True)
            result['runs']=result['runs'][:100]
            remaining=2*1024*1024
            for run in result['runs']:
                if run.get('result'):
                    remaining-=len(json.dumps(run['result']).encode())
                    if remaining<0:run['result']=None;run['result_available']=True
            result['streaming_enabled']=os.environ.get('VDS_STREAMING_ENABLED')=='true'
            result['speech_enabled']=result['streaming_enabled']
            return result
        if method == 'POST' and path == '/api/v2/uploads':
            name, size = body.get('name'), body.get('size')
            if not isinstance(name, str) or len(name) > 200 or not name.lower().endswith(('.csv', '.xlsx')):
                raise RequestError('Choose a CSV or Excel workbook.')
            if type(size) is not int or not 0 < size <= MAX_UPLOAD:
                raise RequestError('Choose a file up to 10 MiB.', 'upload_limit', 413)
            upload_id = uuid.uuid4().hex
            post = self.s3.generate_presigned_post(Bucket=self.bucket, Key=f'{owner}/incoming/{upload_id}',
                Fields={'x-amz-server-side-encryption': 'AES256'},
                Conditions=[['content-length-range', size, size], {'x-amz-server-side-encryption': 'AES256'}], ExpiresIn=300)
            if self.sessions:self.sessions.table.put_item(Item={'pk':owner,'sk':'upload#'+upload_id,'doc':json.dumps({'incoming':True}), 'expires_at':int(time.time())+600})
            return {'ok': True, 'upload_id': upload_id, 'post': post}
        if method == 'POST' and path == '/api/v2/datasets':
            if self.sessions:owner=self.sessions.locate(owners,'upload',body.get('upload_id'))
            return self.call(owner, 'prepare_upload', {k: body.get(k) for k in ['upload_id', 'name', 'question']})
        if method == 'POST' and path == '/api/v2/runs':
            if self.sessions:owner=self.sessions.locate(owners,'dataset',body.get('dataset_id'))
            return self.call(owner, 'submit', {k: body.get(k) for k in ['dataset_id', 'request_key', 'question']})
        if method == 'POST' and path == '/api/v2/stream-tickets':
            if self.sessions:owner=self.sessions.locate(owners,'run',body.get('run_id'))
            return self.call(owner,'stream_ticket',{'run_id':body.get('run_id')})
        if method=='POST' and path=='/api/v2/speech-tickets':
            return self.call(owner,'speech_ticket')
        match = re.fullmatch(r'/api/v2/runs/([a-f0-9]{32})(/cancel)?', path)
        if match and ((method == 'GET' and not match[2]) or (method == 'POST' and match[2])):
            if self.sessions:owner=self.sessions.locate(owners,'run',match[1])
            return self.call(owner, 'cancel' if match[2] else 'run', {'run_id': match[1]})
        match = re.fullmatch(r'/api/v2/runs/([a-f0-9]{32})/(artifacts|events|prepared-data)', path)
        if method == 'GET' and match:
            if self.sessions:owner=self.sessions.locate(owners,'run',match[1])
            query=event.get('queryStringParameters') or {}
            return self.call(owner, match[2].replace('-','_'), {'run_id':match[1], 'after':query.get('after',0),'palette':query.get('palette','decision')})
        match = re.fullmatch(r'/api/v2/datasets/([a-f0-9]{32})/delete', path)
        if method == 'POST' and match:
            if self.sessions:owner=self.sessions.locate(owners,'dataset',match[1])
            return self.call(owner, 'delete', {'dataset_id': match[1]})
        raise RequestError('Endpoint not found.', 'not_found', 404)


def handler(event, context):
    global _gateway
    try:
        if _gateway is None:
            _gateway = Gateway()
        result, status = _gateway.route(event), 200
    except (RequestError,SessionError) as exc:
        status, result = exc.status, {'ok': False, 'error': {'code': exc.code, 'message': str(exc)}}
    except (ValueError, TypeError, UnicodeError):
        status, result = 400, {'ok': False, 'error': {'code': 'invalid_input', 'message': 'Check the request format.'}}
    except Exception as exc:
        # Never log request events, user tokens, presigned policies or source data.
        response=getattr(exc,'response',{})
        logging.getLogger(__name__).error('dependency_failure type=%s aws_code=%s request_id=%s',
            type(exc).__name__,response.get('Error',{}).get('Code','unavailable'),
            response.get('ResponseMetadata',{}).get('RequestId','unavailable'))
        status, result = 503, {'ok': False, 'error': {'code': 'dependency_failure', 'message': 'The workspace service is temporarily unavailable.'}}
    cookies=result.pop('_cookies',[])
    return {'statusCode': status, 'cookies':cookies, 'headers': {'Content-Type': 'application/json', 'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff'}, 'body': json.dumps(result, allow_nan=False)}
