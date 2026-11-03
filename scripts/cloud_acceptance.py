"""Bounded synthetic acceptance against an already deployed AgentCore runtime."""
from __future__ import annotations
import argparse
import base64
import io
import json
import time
import uuid
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analysis_engine.cloud_proxy import CloudProxy


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime-arn',required=True);p.add_argument('--region',default='us-east-1');p.add_argument('--execute',action='store_true');p.add_argument('--output',default='data/cloud-acceptance.json');p.add_argument('--forecast',action='store_true');p.add_argument('--xlsx',action='store_true')
    args=p.parse_args()
    if not args.execute:
        print('Review only: synthetic upload, one quick chart, optional one forecast, status/reconnect checks. Use --execute for an approved live test.');return
    client=CloudProxy(args.runtime_arn,args.region)
    owner='a'*64
    fixture=Path(__file__).resolve().parents[1]/'tests/fixtures/monthly_revenue.csv'
    raw=fixture.read_bytes();name='synthetic_revenue.csv'
    if args.xlsx:
        import csv,openpyxl,datetime
        book=openpyxl.Workbook();book.active.title='Overview';book.active.append(['Monthly business export'])
        ws=book.create_sheet('Transactions');ws.append(['Company revenue export']);ws.append(['When Sold','Net Sales','Business Unit'])
        for row in list(csv.reader(raw.decode().splitlines()))[1:]:
            ws.append([datetime.date.fromisoformat(row[0]),float(row[1]),row[2]])
        buffer=io.BytesIO();book.save(buffer);raw=buffer.getvalue();name='synthetic_business.xlsx'
    uploaded=client.call(owner,'upload',{'name':name,'content_base64':base64.b64encode(raw).decode()})['dataset']
    print(f'Uploaded typed version {uploaded["id"]}; inferred table/header: {uploaded["profile"]["sheet"]}/{uploaded["profile"]["header_row"]}',flush=True)
    evidence={'runtime_arn':args.runtime_arn,'session_id':client.session_id,'dataset':uploaded,'runs':[]}
    questions=['Show monthly revenue']+(['Forecast the next three months'] if args.forecast else [])
    for question in questions:
        run=client.call(owner,'submit',{'dataset_id':uploaded['id'],'question':question,'request_key':str(uuid.uuid4())})['run']
        print(f'{question}: {run["id"]}',flush=True)
        deadline=time.monotonic()+360
        while run['status'] in ['queued','running','reviewing'] and time.monotonic()<deadline:
            time.sleep(2)
            run=client.call(owner,'run',{'run_id':run['id']})['run']
        evidence['runs'].append(run)
        output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(evidence,indent=2))
        print(json.dumps({'status':run['status'],'plan':run.get('plan'),'error':run.get('error'),'summary':(run.get('result') or {}).get('summary')}),flush=True)
        assert run['status']=='succeeded',run.get('error')
        result=run['result']
        assert result['review']['passed']
        if question.startswith('Show'):
            assert len(result['series'])==36 and abs(result['total']-579060)<1e-6
        else:
            assert len(result['forecast'])==3 and result['execution']=='agentcore_code_interpreter'
            assert result['independent_review']['decision']=='accept'
    reopened=CloudProxy(args.runtime_arn,args.region)
    saved=reopened.call(owner,'workspace')
    assert {r['id'] for r in evidence['runs']}.issubset({r['id'] for r in saved['runs']})
    other=reopened.call('b'*64,'workspace');assert all(d['id']!=uploaded['id'] for d in other['datasets'])
    evidence['reconnect_session_id']=reopened.session_id;evidence['reconnect_passed']=True;evidence['owner_isolation_passed']=True
    Path(args.output).write_text(json.dumps(evidence,indent=2))
    print('Live result checks, different-session reconnect and owner isolation passed.',flush=True)


if __name__=='__main__':main()
