"""Bounded hosted-auth acceptance; temporary credentials remain only in memory."""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import boto3
import requests
from botocore.config import Config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--manifest', type=Path, default=Path('docs/deployment/2026-10-31-hosted-web.json'))
    parser.add_argument('--port', type=int, default=12989)
    args = parser.parse_args()
    if not args.execute:
        print('Review only: two temporary no-invite users, JWT/origin/upload isolation checks, then a loopback one-use browser sign-in helper; remove temporary users on finish; browser artifacts follow development retention. No model requests are submitted by this script.')
        return
    outputs = json.loads(args.manifest.read_text())['outputs']
    origin, pool, client_id = outputs['WebUrl'], outputs['UserPoolId'], outputs['ClientId']
    cognito = boto3.client('cognito-idp', region_name='us-east-1', config=Config(connect_timeout=5, read_timeout=20, retries={'total_max_attempts': 1}))
    users, tokens = [], []
    checks = {}
    browser_credentials = None

    def api(token, path, payload=None, expected=200):
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {'x-vds-token': token} if token else {}
        if body is not None:
            headers.update({'Content-Type': 'application/json', 'x-amz-content-sha256': hashlib.sha256(body).hexdigest()})
        with requests.request('POST' if body is not None else 'GET', origin + '/api/v2/' + path,
                              headers=headers, data=body, timeout=70) as response:
            assert response.status_code == expected, (path, response.status_code)
            return response.json()

    def upload(raw, name):
        ticket = api(tokens[0]['AccessToken'], 'uploads', {'name': name, 'size': len(raw), 'owner': 'f' * 64})
        with requests.post(ticket['post']['url'], data=ticket['post']['fields'], files={'file': (name, raw)}, timeout=60) as response:
            assert response.status_code == 204, response.status_code
        return ticket

    def verify_browser():
        workspace = api(tokens[0]['AccessToken'], 'workspace')
        successful = [r for r in workspace['runs'] if r['status'] == 'succeeded']
        assert any(r['result']['task'] == 'monthly_summary' for r in successful)
        forecasts = [r for r in successful if r['result']['task'] == 'forecast']
        assert forecasts, 'Complete the forecast in the hosted browser first.'
        evidence = api(tokens[0]['AccessToken'], 'runs/' + forecasts[0]['id'])['run']
        result = evidence['result']
        assert result['execution'] == 'agentcore_code_interpreter' and result['review']['passed']
        assert len(result['forecast']) == 3 and result['independent_review']['decision'] == 'accept'
        api(tokens[1]['AccessToken'], 'runs/' + evidence['id'], expected=404)
        session = result['sandbox']['session_id']
        state = boto3.client('bedrock-agentcore', region_name='us-east-1').get_code_interpreter_session(codeInterpreterIdentifier='aws.codeinterpreter.v1', sessionId=session)
        assert state['status'] == 'TERMINATED'
        checks.update({'hosted_browser_chart_forecast': True, 'other_user_result_denied': True, 'sandbox_terminated': True})
        Path('data/hosted-browser-acceptance.json').write_text(json.dumps(evidence, indent=2) + '\n')
        summary = {'origin': origin, 'checks': checks, 'run_id': evidence['id'], 'execution': result['execution'],
                   'release': result['evidence']['release'], 'timing_ms': result['timing_ms'],
                   'sandbox_session': session, 'sandbox_status': state['status'], 'test': result['test'],
                   'independent_review': result['independent_review']}
        Path('docs/deployment/2026-10-31-hosted-acceptance.json').write_text(json.dumps(summary, indent=2) + '\n')
        return summary

    try:
        for _ in range(2):
            username = 'vds-check-' + uuid.uuid4().hex
            password = secrets.token_urlsafe(30) + 'aA1!'
            cognito.admin_create_user(UserPoolId=pool, Username=username, MessageAction='SUPPRESS')
            users.append(username)
            cognito.admin_set_user_password(UserPoolId=pool, Username=username, Password=password, Permanent=True)
            result = cognito.admin_initiate_auth(UserPoolId=pool, ClientId=client_id, AuthFlow='ADMIN_USER_PASSWORD_AUTH', AuthParameters={'USERNAME': username, 'PASSWORD': password})
            tokens.append(result['AuthenticationResult'])
            if browser_credentials is None: browser_credentials = {'username': username, 'password': password}
            password = None
        api(None, 'workspace', expected=401)
        api('invalid-user-token', 'workspace', expected=401)
        api(tokens[0]['IdToken'], 'workspace', expected=401)
        with requests.get(outputs['GatewayOriginUrl'] + 'api/v2/workspace', timeout=20) as response:
            assert response.status_code == 403
        with requests.get(f'https://{outputs["SiteBucket"]}.s3.us-east-1.amazonaws.com/index.html', timeout=20) as response:
            assert response.status_code == 403
        checks.update({'anonymous_denied': True, 'invalid_and_id_tokens_denied': True, 'direct_lambda_denied': True, 'direct_static_bucket_denied': True})
        api(tokens[0]['AccessToken'], 'uploads', {'name': 'too-large.csv', 'size': 10 * 1024 * 1024 + 1}, expected=413)
        raw = (Path(__file__).resolve().parents[1] / 'tests/fixtures/monthly_revenue.csv').read_bytes()
        ticket = upload(raw, 'hosted-auth-fixture.csv')
        bad_fields = {**ticket['post']['fields'], 'key': 'f' * 64 + '/incoming/' + ticket['upload_id']}
        with requests.post(ticket['post']['url'], data=bad_fields, files={'file': ('hosted-auth-fixture.csv', raw)}, timeout=20) as response:
            assert response.status_code == 403
        api(tokens[1]['AccessToken'], 'datasets', {'upload_id': ticket['upload_id'], 'name': 'hosted-auth-fixture.csv'}, expected=404)
        dataset = api(tokens[0]['AccessToken'], 'datasets', {'upload_id': ticket['upload_id'], 'name': 'hosted-auth-fixture.csv'})['dataset']
        assert dataset['profile']['rows'] == 72
        assert not api(tokens[1]['AccessToken'], 'workspace')['datasets']
        checks.update({'owner_spoof_ignored': True, 'post_key_tampering_denied': True, 'other_user_staged_upload_denied': True, 'other_user_workspace_isolated': True, 'oversize_rejected': True})
        row = b'2025-01-01,1,' + b'x' * 10000 + b'\n'
        large = b'date,revenue,note\n'
        large += row * ((10 * 1024 * 1024 - len(large)) // len(row))
        remaining = 10 * 1024 * 1024 - len(large)
        large += b'2025-01-01,1,' + b'x' * (remaining - len(b'2025-01-01,1,') - 1) + b'\n'
        assert len(large) == 10 * 1024 * 1024
        ticket = upload(large, 'exact-ten-mib.csv')
        large_dataset = api(tokens[0]['AccessToken'], 'datasets', {'upload_id': ticket['upload_id'], 'name': 'exact-ten-mib.csv'})['dataset']
        assert large_dataset['profile']['rows'] > 1000
        api(tokens[0]['AccessToken'], 'datasets/' + large_dataset['id'] + '/delete', {})
        api(tokens[0]['AccessToken'], 'datasets/' + dataset['id'] + '/delete', {})
        checks['exact_ten_mib_prepared_and_deleted'] = True

        class BrowserHelper(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                nonlocal browser_credentials
                try:
                    if self.path == '/browser-login' and browser_credentials is not None:
                        result, browser_credentials = browser_credentials, None
                    elif self.path == '/verify': result = verify_browser()
                    elif self.path == '/finish':
                        result = {'finished': True}
                        threading.Thread(target=self.server.shutdown, daemon=True).start()
                    else:
                        self.send_error(404); return
                    body = json.dumps(result).encode()
                    self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(body)
                except Exception as exc:
                    self.send_error(409, 'Acceptance check incomplete: ' + type(exc).__name__)

        server = HTTPServer(('127.0.0.1', args.port), BrowserHelper)
        timer = threading.Timer(900, server.shutdown); timer.daemon = True; timer.start()
        print(json.dumps({'ready': True, 'origin': origin, 'checks': checks, 'helper_port': args.port}), flush=True)
        try: server.serve_forever()
        finally: server.server_close(); timer.cancel()
    finally:
        # Delete only the synthetic accounts created by this invocation, no invites.
        for username in users:
            cognito.admin_delete_user(UserPoolId=pool, Username=username)
        browser_credentials = None; tokens.clear()
        print('Removed temporary acceptance users; no credentials saved.', flush=True)


if __name__ == '__main__': main()
