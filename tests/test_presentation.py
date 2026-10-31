import ast
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from analysis_engine.ingestion import parse_table, write_parquet
from analysis_engine.planning import local_plan
from analysis_engine.presentation import recommendations, enrich_result
from analysis_engine.tabular import forecast_result, quick_result
from analysis_engine.exports import build_bundle, themed_bundle, PALETTES
from analysis_engine.telemetry import emit, safe_error


class ExperienceTests(unittest.TestCase):
    def setUp(self):
        self.raw = (Path(__file__).parent/'fixtures/monthly_revenue.csv').read_bytes()
        self.table, self.profile = parse_table('sales.csv', self.raw)
        self.dataset = {'id':'a'*32, 'profile':self.profile}

    def test_suggestions_are_eligible_and_do_not_fit(self):
        experience = recommendations(self.table,self.profile)
        self.assertEqual([s['id'] for s in experience['suggestions']], ['monthly_summary','forecast'])
        self.assertIn('36 consecutive months', experience['suggestions'][1]['why'])
        short = self.table.slice(0,10)
        self.assertEqual([s['id'] for s in recommendations(short,self.profile)['suggestions']], ['monthly_summary'])
        gapped = self.table.take([i for i in range(self.table.num_rows) if i not in (2,3)])
        self.assertEqual(len(recommendations(gapped,self.profile)['suggestions']), 1)

    def test_ambiguous_missing_nonadditive_and_duplicate_profiles(self):
        from copy import deepcopy
        profile=deepcopy(self.profile)
        profile['columns'].append(dict(profile['columns'][0],name='payment_date'))
        self.assertEqual(recommendations(self.table,profile)['suggestions'],[])
        profile=deepcopy(self.profile);profile['columns'][1]['missing']=1
        self.assertEqual(recommendations(self.table,profile)['suggestions'],[])
        profile=deepcopy(self.profile);profile['columns'][1]['units']='%'
        self.assertEqual(recommendations(self.table,profile)['suggestions'],[])
        profile=deepcopy(self.profile);profile['duplicates']=1
        self.assertEqual(len(recommendations(self.table,profile)['suggestions']),1)

    def test_forecast_figures_preserve_validation_and_test_lineage(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'dataset.parquet';write_parquet(self.table,path)
            plan=local_plan(self.dataset,{'question':'Forecast next three months'})
            result=enrich_result(forecast_result(path,plan),plan)
        self.assertEqual([v['split'] for v in result['visuals']], ['observed','test','validation'])
        self.assertEqual(result['visuals'][1]['figure']['data'][1]['y'],result['test']['predictions'])
        self.assertEqual(result['visuals'][2]['figure']['data'][0]['y'],[c['validation_mae'] for c in result['candidates'].values()])
        selected=[m for m in result['methodology'] if m.get('disposition')=='Selected on validation MAE']
        self.assertEqual(selected[0]['id'], result['selected_method'])
        self.assertTrue(all(v['dataset_version']==self.dataset['id'] for v in result['visuals']))

    def test_bundle_contains_reproducible_support_and_no_source_data(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'dataset.parquet';write_parquet(self.table,path)
            plan=local_plan(self.dataset,{'question':'Show monthly revenue'})
            result=enrich_result(quick_result(path,plan),plan)
            bundle=build_bundle({'plan':plan.model_dump()},result)
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            for required in ('analysis.py','visualization.py','vds_recipe.py','ingestion.py','plan.json','analysis.ipynb','series.csv','figures.json','requirements.txt'):
                self.assertIn(required,archive.namelist())
            self.assertNotIn('dataset.parquet',archive.namelist())
            for name in archive.namelist():
                if name.endswith('.py'):ast.parse(archive.read(name).decode())
            self.assertEqual(json.loads(archive.read('figures.json'))[0]['data'][0]['y'],[r['value'] for r in result['series']])
        with zipfile.ZipFile(io.BytesIO(themed_bundle(bundle,'ocean'))) as themed:
            self.assertEqual(json.loads(themed.read('figures.json'))[0]['layout']['colorway'],PALETTES['ocean'])
            self.assertEqual(json.loads(themed.read('figures.json'))[0]['data'][0]['y'],[r['value'] for r in result['series']])

    def test_telemetry_excludes_sensitive_values_and_run_ids_as_dimensions(self):
        with self.assertLogs('vds.telemetry',level='INFO') as output:
            emit(event='stage',stage='analysis',status='completed',duration_ms=20,run_id='a'*32,prompt='secret-prompt',token='secret-token',error_code='secret source value')
            safe_error(ValueError('secret-prompt'))
        text=' '.join(output.output)
        self.assertNotIn('secret',text)
        record=json.loads(output.output[0].split('vds.telemetry:',1)[1])
        self.assertNotIn('run_id',record['_aws']['CloudWatchMetrics'][0]['Dimensions'][0])


if __name__=='__main__':unittest.main()
