from __future__ import annotations
import concurrent.futures
import copy
import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import openpyxl
import pyarrow.parquet as pq
from analysis_engine.ingestion import InputError, parse_table, write_parquet
from analysis_engine.planning import local_plan, strands_plan
from analysis_engine.tabular import forecast_result, review_forecast, supervised_result, review_supervised
from analysis_engine.workspace import Workspace

FIXTURE = Path(__file__).parent / 'fixtures/monthly_revenue.csv'


class IngestionTests(unittest.TestCase):
    def test_types_identifiers_roundtrip(self):
        table,profile=parse_table('x.csv',b'id,date,revenue\n001,2024-01-01,2.5\n002,2024-02-01,3\n')
        self.assertEqual(table['id'].to_pylist(),['001','002'])
        self.assertEqual([c['role'] for c in profile['columns']],['identifier','time','measure'])
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'data.parquet';write_parquet(table,path)
            self.assertTrue(pq.read_table(path).equals(table))

    def test_explicit_workbook_sheet_and_header(self):
        book=openpyxl.Workbook();book.active.title='Summary';book.create_sheet('Data')
        book['Data'].append(['Title']);book['Data'].append(['date','revenue']);book['Data'].append(['2024-01-01',50])
        buffer=io.BytesIO();book.save(buffer)
        automatic,profile=parse_table('x.xlsx',buffer.getvalue())
        self.assertEqual(profile['sheet'],'Data')
        self.assertEqual(profile['header_row'],2)
        self.assertEqual(automatic.num_rows,1)
        table,_=parse_table('x.xlsx',buffer.getvalue(),'Data',2)
        self.assertEqual(table.num_rows,1)
        self.assertEqual(table['revenue'].to_pylist(),[50.])
        book['Data']['B3']='=1+2';buffer=io.BytesIO();book.save(buffer)
        with self.assertRaisesRegex(InputError,'formulas'):parse_table('x.xlsx',buffer.getvalue(),'Data',2)

    def test_malformed_and_duplicate_input_rejected(self):
        for raw in [b'a,a\n1,2',b'a,b\n1,2,3',b'a\n',b'date\n2024-02-31',b'v\n1e999']:
            with self.subTest(raw=raw),self.assertRaises(InputError):parse_table('x.csv',raw)
        with self.assertRaises(InputError):parse_table('x.zip',b'abcd')


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.w=Workspace(self.temp.name)
        self.dataset=self.w.ingest('alice','sales.csv',FIXTURE.read_bytes())
        self.payload={'dataset_id':self.dataset['id'],'request_key':'q1','question':'Show monthly revenue'}

    def tearDown(self):
        for t in self.w.threads:t.join(10)
        self.temp.cleanup()

    def test_upload_is_immutable_and_profile_persisted(self):
        second=self.w.ingest('alice','sales.csv',FIXTURE.read_bytes())
        self.assertNotEqual(second['id'],self.dataset['id'])
        folder=Path(self.temp.name)/self.dataset['id']
        self.assertEqual((folder/'source').read_bytes(),FIXTURE.read_bytes())
        reopened=Workspace(self.temp.name)
        self.assertEqual(reopened.dataset('alice',self.dataset['id']),self.dataset)
        with self.assertRaises(InputError):reopened.dataset('bob',self.dataset['id'])

    def test_quick_chart_persistence_ownership_idempotency(self):
        with patch('analysis_engine.tabular.forecast_result',side_effect=AssertionError('ML called')):
            run=self.w.submit('alice',self.payload)
        self.assertEqual(run['status'],'succeeded',run)
        self.assertEqual(run['result']['total'],579060)
        self.assertEqual(len(run['result']['series']),36)
        self.assertTrue(run['result']['review']['passed'])
        self.assertEqual(self.w.submit('alice',self.payload)['id'],run['id'])
        with self.assertRaises(InputError) as e:self.w.submit('alice',{**self.payload,'question':'Different question'})
        self.assertEqual(e.exception.code,'idempotency_conflict')
        with self.assertRaises(InputError):self.w.run('bob',run['id'])
        self.assertEqual(Workspace(self.temp.name).run('alice',run['id'])['result'],run['result'])

    def test_parallel_requests_commit_once(self):
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            runs=list(pool.map(lambda _: self.w.submit('alice',self.payload),range(4)))
        self.assertEqual(len({r['id'] for r in runs}),1)
        self.assertEqual(len(self.w.list('alice')['runs']),1)

    def test_deep_forecast_and_quick_same_version(self):
        quick=self.w.submit('alice',self.payload)
        deep=self.w.submit('alice',{**self.payload,'task':'forecast','question':'Forecast the next three months','request_key':'f1'})
        for thread in self.w.threads:thread.join(30)
        run=self.w.run('alice',deep['id'])
        self.assertEqual(run['status'],'succeeded',run)
        self.assertEqual(run['dataset_id'],quick['dataset_id'])
        self.assertEqual(run['prior_run_id'],quick['id'])
        self.assertEqual(run['plan']['revision'],2)
        self.assertEqual(len(run['result']['forecast']),3)
        self.assertEqual(run['result']['forecast'][0]['month'],'2026-01')
        self.assertIn('recipe_source',run['result']['evidence'])

    def test_capacity_cancel_restart_and_stale_completion(self):
        with patch.object(self.w,'deep'):
            deep=self.w.submit('alice',{**self.payload,'task':'forecast'})
            with self.assertRaises(InputError) as e:self.w.submit('alice',{**self.payload,'task':'forecast','request_key':'f2'})
            self.assertEqual(e.exception.code,'capacity_exceeded')
            # Quick capacity stays available while deep work is admitted.
            quick=self.w.submit('alice',{**self.payload,'request_key':'quick'})
            self.assertEqual(quick['status'],'succeeded')
            self.w.cancel('alice',deep['id'])
            self.assertFalse(self.w.update('alice',deep['id'],status='succeeded'))
            self.assertEqual(self.w.run('alice',deep['id'])['status'],'cancelled')
            another=self.w.submit('alice',{**self.payload,'task':'forecast','request_key':'f3'})
            self.w.recover()
            self.assertEqual(self.w.run('alice',another['id'])['status'],'interrupted')

    def test_delete_revokes_data_runs_and_artifacts(self):
        run=self.w.submit('alice',self.payload)
        self.w.delete('alice',self.dataset['id'])
        with self.assertRaises(InputError):self.w.run('alice',run['id'])
        with self.assertRaises(InputError):self.w.dataset('alice',self.dataset['id'])
        self.assertEqual(self.w.list('alice'),{'datasets':[],'runs':[],'mode':'local_demo','cloud_enabled':False})
        self.assertFalse((Path(self.temp.name)/self.dataset['id']).exists())
        self.assertNotIn(b'Show monthly revenue',(Path(self.temp.name)/'workspace.sqlite').read_bytes())

    def test_ambiguous_metric_and_missing_values_need_clarification(self):
        with self.assertRaises(InputError) as required:
            self.w.submit("alice",{**self.payload,"research_requirement":"required"})
        self.assertEqual(required.exception.code,"research_unavailable")
        d=self.w.ingest('alice','x.csv',b'date,net_revenue,gross_revenue\n2024-01-01,1,2')
        with self.assertRaises(InputError) as e:local_plan(d,{'question':'Show revenue'})
        self.assertEqual(e.exception.code,'clarification_required')
        d=self.w.ingest('alice','x.csv',b'date,revenue\n2024-01-01,1\n2024-02-01,')
        r=self.w.submit('alice',{'dataset_id':d['id'],'request_key':'missing','question':'Show monthly revenue'})
        self.assertEqual(r['error']['code'],'readiness_failed')

    def test_forecast_review_rejects_false_metrics_and_partitions(self):
        plan=local_plan(self.dataset,{**self.payload,'task':'forecast'})
        path=Path(self.temp.name)/self.dataset['id']/'dataset.parquet'
        result=forecast_result(path,plan)
        for mutate in [lambda r:r['test'].update(mae=99999),lambda r:r['split'].update(train_end=35),lambda r:r['series'][0].update(value=42),lambda r:r['test']['baseline_predictions'].__setitem__(0,123)]:
            wrong=copy.deepcopy(result);mutate(wrong)
            with self.assertRaises(InputError) as e:review_forecast(path,plan,wrong)
            self.assertEqual(e.exception.code,'evidence_rejected')

    def test_missing_months_not_filled(self):
        d=self.w.ingest('alice','gaps.csv',FIXTURE.read_bytes().replace(b'2024-02-01',b'2024-03-01'))
        plan=local_plan(d,{'question':'Forecast revenue','task':'forecast'})
        with self.assertRaisesRegex(InputError,'consecutive'):forecast_result(Path(self.temp.name)/d['id']/'dataset.parquet',plan)

    def test_strands_plan_contract_validates_model_output(self):
        plan=local_plan(self.dataset,self.payload)
        agent=Mock(return_value=SimpleNamespace(structured_output=plan))
        self.assertEqual(strands_plan(self.dataset,self.payload,agent).planner,'strands')
        prompt=agent.call_args.args[0]
        self.assertNotIn('579060',prompt)
        wrong=plan.model_copy(update={'dataset_version':'other'})
        agent.return_value=SimpleNamespace(structured_output=wrong)
        with self.assertRaises(InputError):strands_plan(self.dataset,self.payload,agent)

    def test_regression_classification_and_leakage(self):
        import numpy as np
        rng=np.random.default_rng(42)
        for task in ['regression','classification']:
            rows=['x,z,target']
            for i in range(200):
                x,z=rng.normal(size=2)
                target=3*x+z+rng.normal(scale=.1) if task=='regression' else ('yes' if x+z>0 else 'no')
                rows.append(f'{x},{z},{target}')
            d=self.w.ingest('alice','training.csv','\n'.join(rows).encode())
            p=local_plan(d,{'question':'Predict target','task':task,'metric':'target','features':['x','z']})
            self.assertIn('independent row',p.definition)
            path=Path(self.temp.name)/d['id']/'dataset.parquet'
            result=supervised_result(path,p)
            self.assertTrue(result['review']['passed'])
            self.assertNotEqual(result['selected_method'],'dummy')
            key='mae' if task=='regression' else 'balanced_accuracy'
            wrong=copy.deepcopy(result);wrong['test'][key]=123
            with self.assertRaises(InputError):review_supervised(path,p,wrong)
            wrong=copy.deepcopy(result);wrong['split']['train'].append(wrong['split']['test'][0])
            with self.assertRaises(InputError):review_supervised(path,p,wrong)
            with self.assertRaises(InputError):local_plan(d,{'question':'Predict','task':task,'metric':'target','features':['target']})
        d=self.w.ingest('alice','leak.csv',('x,target\n'+'\n'.join(f'{i},{i}' for i in range(100))).encode())
        p=local_plan(d,{'question':'Predict','task':'regression','metric':'target','features':['x']})
        with self.assertRaises(InputError) as e:supervised_result(Path(self.temp.name)/d['id']/'dataset.parquet',p)
        self.assertEqual(e.exception.code,'leakage_rejected')


if __name__=='__main__':unittest.main()
