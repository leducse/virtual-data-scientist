"""Synthetic cancellation, input, identity and deletion checks on a dev runtime."""
from __future__ import annotations

import argparse
import base64
import io
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analysis_engine.cloud_proxy import CloudProxy
from analysis_engine.ingestion import InputError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-arn', required=True)
    parser.add_argument('--region', default='us-east-1')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output', default='data/cloud-safety-acceptance.json')
    args = parser.parse_args()
    if not args.execute:
        print('Review only: synthetic invalid uploads, one immediately cancelled analysis, identity/idempotency and deletion checks. Use --execute for an approved dev test.')
        return
    client = CloudProxy(args.runtime_arn, args.region)
    owner, other = 'c' * 64, 'd' * 64
    evidence = {'runtime_arn': args.runtime_arn, 'checks': {}}

    def upload(name, raw):
        return client.call(owner, 'upload', {'name': name, 'content_base64': base64.b64encode(raw).decode()})['dataset']

    def rejects(label, action, codes):
        try:
            action()
        except InputError as exc:
            assert exc.code in codes, (label, exc.code)
            evidence['checks'][label] = {'passed': True, 'code': exc.code, 'message': str(exc)}
        else:
            raise AssertionError(label + ' unexpectedly succeeded')

    rejects('malformed_csv', lambda: upload('invalid.csv', b'date,revenue\n2025-01-01,10,extra'), {'invalid_input', 'clarification_required'})
    import openpyxl
    book = openpyxl.Workbook()
    for ws in [book.active, book.create_sheet('Other business')]:
        ws.append(['Date', 'Revenue'])
        ws.append(['2025-01-01', 20])
    buffer = io.BytesIO()
    book.save(buffer)
    rejects('ambiguous_workbook', lambda: upload('ambiguous.xlsx', buffer.getvalue()), {'clarification_required'})

    fixture = Path(__file__).resolve().parents[1] / 'tests/fixtures/monthly_revenue.csv'
    dataset = upload('synthetic_cancel.csv', fixture.read_bytes())
    request = {'dataset_id': dataset['id'], 'question': 'Forecast the next three months', 'request_key': str(uuid.uuid4())}
    run = client.call(owner, 'submit', request)['run']
    cancelled = client.call(owner, 'cancel', {'run_id': run['id']})['run']
    assert cancelled['status'] == 'cancelled', cancelled['status']
    repeat = client.call(owner, 'submit', request)['run']
    assert repeat['id'] == run['id'] and repeat['status'] == 'cancelled'
    evidence['checks']['idempotent_submission'] = {'passed': True, 'run_id': run['id']}
    rejects('idempotency_conflict', lambda: client.call(owner, 'submit', {**request, 'question': 'Show monthly revenue'}), {'idempotency_conflict'})
    rejects('other_owner_run', lambda: client.call(other, 'run', {'run_id': run['id']}), {'not_found'})
    rejects('other_owner_delete', lambda: client.call(other, 'delete', {'dataset_id': dataset['id']}), {'not_found'})
    time.sleep(8)  # Give an in-flight planner time to observe cancellation.
    after = client.call(owner, 'run', {'run_id': run['id']})['run']
    assert after['status'] == 'cancelled' and not after.get('result_key') and not after.get('result')
    evidence['checks']['cancel_no_late_publication'] = {'passed': True, 'run_id': run['id'], 'observed_after_seconds': 8}
    assert client.call(owner, 'delete', {'dataset_id': dataset['id']})['deleted']
    rejects('deleted_dataset_run', lambda: client.call(owner, 'run', {'run_id': run['id']}), {'not_found'})
    workspace = CloudProxy(args.runtime_arn, args.region).call(owner, 'workspace')
    assert all(d['id'] != dataset['id'] for d in workspace['datasets'])
    evidence['checks']['delete_reconnect'] = {'passed': True, 'dataset_id': dataset['id']}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
