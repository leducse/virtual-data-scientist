"""Small synthetic measurement; no cloud calls or production capacity claims."""
from __future__ import annotations
import json
import statistics
import tempfile
import time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analysis_engine.workspace import Workspace


def main():
    with tempfile.TemporaryDirectory() as root:
        service=Workspace(root)
        dataset=service.ingest('benchmark','synthetic.csv',(Path(__file__).resolve().parents[1]/'tests/fixtures/monthly_revenue.csv').read_bytes())
        def quick(key):
            run=service.submit('benchmark',{'dataset_id':dataset['id'],'request_key':key,'question':'Show monthly revenue'})
            assert run['status']=='succeeded' and run['result']['total']==579060
            return run['result']['timing_ms']['end_to_end']
        first=quick('first')
        warm=[quick(f'warm-{i}') for i in range(5)]
        deep=service.submit('benchmark',{'dataset_id':dataset['id'],'request_key':'forecast','question':'Forecast the next three months','task':'forecast'})
        concurrent=[quick(f'concurrent-{i}') for i in range(3)]
        for thread in service.threads:thread.join(125)
        result=service.run('benchmark',deep['id'])
        assert result['status']=='succeeded' and len(result['result']['forecast'])==3,result
        print(json.dumps({'date':'2026-10-31','environment':'local macOS / Python '+sys.version.split()[0],
            'fixture':{'rows':72,'months':36,'total':579060},'upload_profile_ms':dataset['timing_ms']['ingestion'],
            'first_query_in_process_ms':first,'subsequent_query_ms':{'n':5,'observations':warm,'median':statistics.median(warm)},
            'query_after_deep_admission_ms':{'n':3,'observations':concurrent,'median':statistics.median(concurrent)},
            'deep_fresh_process_ms':result['result']['timing_ms']['end_to_end'],
            'test_mae':result['result']['test']['mae'],'naive_test_mae':result['result']['test']['baseline_mae'],
            'versions':result['result']['versions'],'limits':'Tiny synthetic fixture; no HTTP overhead, production load, p95/p99 or cloud latency inference.'},indent=2))


if __name__=='__main__':main()
