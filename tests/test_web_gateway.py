import io
import json
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import jwt
from botocore.exceptions import ClientError
from cryptography.hazmat.primitives.asymmetric import rsa

from aws_backend.web_gateway import Gateway, Identity, RequestError


class GatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.keys = Mock()
        self.keys.get_signing_key_from_jwt.return_value = SimpleNamespace(key=self.key.public_key())
        self.identity = Identity('https://example.test/pool', 'client1', self.keys)
        self.env = patch.dict(os.environ, {'VDS_RUNTIME_ARN': 'arn:test:runtime', 'VDS_DATA_BUCKET': 'test-data'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.runtime, self.s3 = Mock(), Mock()
        self.gateway = Gateway(self.identity, self.runtime, self.s3)

    def token(self, **changes):
        claims = {'iss': self.identity.issuer, 'client_id': 'client1', 'token_use': 'access',
                  'sub': 'opaque-cognito-subject', 'iat': int(time.time()) - 5, 'exp': int(time.time()) + 300}
        claims.update(changes)
        return jwt.encode(claims, self.key, algorithm='RS256')

    def event(self, method='GET', path='/api/v2/workspace', body=None, token=None):
        return {'requestContext': {'http': {'method': method}}, 'rawPath': path,
                'headers': {'x-vds-token': token or self.token(), 'content-type': 'application/json'},
                'body': json.dumps(body) if body is not None else ''}

    def test_identity_requires_valid_access_token_for_exact_issuer_and_client(self):
        owner = self.identity.owner(self.token())
        self.assertEqual(len(owner), 64)
        self.assertNotEqual(owner, self.identity.owner(self.token(sub='another-user')))
        for changes in [{'token_use': 'id'}, {'client_id': 'other'}, {'iss': 'https://evil.test/pool'},
                        {'exp': int(time.time()) - 2}, {'sub': ''}, {'iat': int(time.time()) + 1000}]:
            with self.subTest(changes=changes), self.assertRaises(RequestError):
                self.identity.owner(self.token(**changes))
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with self.assertRaises(RequestError):
            self.identity.owner(jwt.encode({'sub': 'x'}, other, algorithm='RS256'))
        with self.assertRaises(RequestError): self.identity.owner(None)
        with self.assertRaises(RequestError): self.identity.owner('x' * 16001)

    def test_verified_subject_overrides_payload_owner_and_runtime_session(self):
        self.runtime.invoke_agent_runtime.return_value = {'response': io.BytesIO(b'{"ok":true,"run":{"id":"r"}}')}
        body = {'owner': 'a' * 64, 'dataset_id': 'd', 'request_key': 'k', 'question': 'Show monthly revenue'}
        self.gateway.route(self.event('POST', '/api/v2/runs', body))
        args = self.runtime.invoke_agent_runtime.call_args.kwargs
        payload = json.loads(args['payload'])
        self.assertEqual(payload['owner'], self.identity.owner(self.token()))
        self.assertNotEqual(payload['owner'], body['owner'])
        self.assertNotIn('owner', payload['payload'])
        self.assertEqual(args['runtimeSessionId'], payload['owner'])

    def test_presigned_policy_is_exact_size_owner_and_five_minutes(self):
        self.s3.generate_presigned_post.return_value = {'url': 'https://example.test', 'fields': {}}
        response = self.gateway.route(self.event('POST', '/api/v2/uploads', {'name': 'sales.csv', 'size': 1234, 'key': 'somebody-else'}))
        args = self.s3.generate_presigned_post.call_args.kwargs
        self.assertEqual(args['Key'], self.identity.owner(self.token()) + '/incoming/' + response['upload_id'])
        self.assertEqual(args['ExpiresIn'], 300)
        self.assertIn(['content-length-range', 1234, 1234], args['Conditions'])
        for size in [0, -1, 10 * 1024 * 1024 + 1, True]:
            with self.subTest(size=size), self.assertRaises(RequestError):
                self.gateway.route(self.event('POST', '/api/v2/uploads', {'name': 'sales.csv', 'size': size}))

    def test_no_client_paths_or_source_bytes_forwarded(self):
        self.runtime.invoke_agent_runtime.return_value = {'response': io.BytesIO(b'{"ok":true,"dataset":{}}')}
        self.gateway.route(self.event('POST', '/api/v2/datasets', {'upload_id': 'u', 'name': 'f.csv', 'key': 'other/key', 'bucket': 'evil', 'content_base64': 'x'}))
        data = json.loads(self.runtime.invoke_agent_runtime.call_args.kwargs['payload'])
        self.assertEqual(set(data['payload']), {'upload_id', 'name', 'question'})
        with self.assertRaises(RequestError): self.gateway.route(self.event('GET', '/api/v1/admin'))
        self.assertEqual(self.runtime.invoke_agent_runtime.call_count, 1)

    def test_limits_before_runtime_and_no_anonymous_actions(self):
        event = self.event('POST', '/api/v2/runs', {})
        event['headers'].pop('x-vds-token')
        with self.assertRaises(RequestError): self.gateway.route(event)
        event = self.event('POST', '/api/v2/runs', {'huge': 'x' * 66000})
        with self.assertRaises(RequestError): self.gateway.route(event)
        self.runtime.invoke_agent_runtime.assert_not_called()

    def test_dependency_logs_exclude_tokens_and_provider_error_messages(self):
        import aws_backend.web_gateway as module
        service=Mock()
        service.route.side_effect=ClientError({'Error':{'Code':'AccessDeniedException','Message':'sensitive-sentinel'}},'InvokeAgentRuntime')
        with patch.object(module,'_gateway',service),self.assertLogs(module.__name__,level='ERROR') as logs:
            result=module.handler({'headers':{'x-vds-token':'sensitive-sentinel'}},None)
        self.assertEqual(result['statusCode'],503)
        self.assertIn('AccessDeniedException',''.join(logs.output))
        self.assertNotIn('sensitive-sentinel',''.join(logs.output)+result['body'])


if __name__ == '__main__': unittest.main()
