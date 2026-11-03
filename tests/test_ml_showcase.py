import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

from analysis_engine.public_datasets import load,catalog
from analysis_engine.ingestion import parse_table,write_parquet,InputError
from analysis_engine.planning import local_plan
from analysis_engine.tabular import supervised_result,unsupervised_result,review_supervised,review_unsupervised,forecast_result,review_forecast
from analysis_engine.presentation import recommendations,enrich_result
from analysis_engine.exports import build_bundle
from analysis_engine.agent_workflow import run_forecast,AnalystProgram,AnalyticalReview,analytical_facts
from analysis_engine.code_policy import validate_sealed_program

CASES=[('iris','classification'),('diabetes','regression'),('penguins','classification'),('blobs','clustering'),('wine','pca'),('sales','anomaly_detection')]


def prepared(folder,sample,task):
    raw,metadata=load(sample);table,profile=parse_table(sample+'.csv',raw);profile['teaching']=metadata
    dataset={'id':'a'*32,'profile':profile};plan=local_plan(dataset,{'question':metadata['question'],'task':task})
    path=Path(folder)/'dataset.parquet';write_parquet(table,path)
    return dataset,plan,path,table


def wrapper(task):
    name='supervised_result' if task in {'regression','classification'} else 'unsupervised_result'
    return f'import json\nfrom types import SimpleNamespace\nfrom vds_recipe import {name}\nwith open("plan.json") as source:\n    plan=SimpleNamespace(**json.load(source))\nresult={name}("dataset.parquet",plan)\nprint("VDS_RESULT="+json.dumps(result))'


class MLShowcaseTests(unittest.TestCase):
    def test_forecast_training_grid_is_recorded_checked_and_exported(self):
        with tempfile.TemporaryDirectory() as folder:
            _,plan,path,_=prepared(folder,'sales','forecast')
            result=forecast_result(path,plan)
            self.assertEqual(result['candidates']['holt']['fit']['grid_size'],12)
            self.assertEqual(result['candidates']['holt']['fit']['selection'],'training_sse')
            for stage in ('validation','future'):
                bad=copy.deepcopy(result)
                target=bad['candidates']['holt']['fit'] if stage=='validation' else bad['fitting']['future']
                target['initial_level']=999999
                with self.assertRaises(InputError):review_forecast(path,plan,bad)
            with zipfile.ZipFile(io.BytesIO(build_bundle({'plan':plan.model_dump()},result))) as archive:archive.extractall(folder)
            code=(Path(folder)/'analysis.py').read_text();self.assertIn('def fit_holt',code);self.assertIn('optimized=False',code)
            execution=subprocess.run([sys.executable,'analysis.py'],cwd=folder,env={**os.environ,'OPENBLAS_NUM_THREADS':'1','PYTHONPATH':folder},capture_output=True,text=True,timeout=45)
            self.assertEqual(execution.returncode,0,execution.stderr)

    def test_all_tasks_check_source_and_export_runnable_notebooks(self):
        for sample,task in CASES:
            with self.subTest(task=task,sample=sample),tempfile.TemporaryDirectory() as folder:
                dataset,plan,path,table=prepared(folder,sample,task)
                self.assertEqual(plan.max_candidates,5 if task=='clustering' else 2 if task in {'classification','regression'} else 1)
                if sample=='sales':self.assertIn('revenue',plan.features);self.assertIsNone(plan.metric)
                result=(supervised_result if task in {'regression','classification'} else unsupervised_result)(path,plan)
                review=(review_supervised if task in {'regression','classification'} else review_unsupervised)(path,plan,result)
                self.assertTrue(review['passed']);result['review']=review;enrich_result(result,plan)
                self.assertGreaterEqual(len(result['visuals']),3)
                self.assertTrue(recommendations(table,dataset['profile'])['suggestions'])
                data=build_bundle({'plan':plan.model_dump()},result)
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    archive.extractall(folder)
                code=(Path(folder)/'analysis.py').read_text()
                self.assertIn('from sklearn',code);self.assertIn('.fit(',code)
                env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','PYTHONPATH':folder}
                execution=subprocess.run([sys.executable,'analysis.py'],cwd=folder,env=env,capture_output=True,text=True,timeout=45)
                self.assertEqual(execution.returncode,0,execution.stderr)
                self.assertTrue((Path(folder)/'reproduced-result.json').exists())
                # Execute every notebook code cell, including offline Plotly figure export.
                notebook=json.loads((Path(folder)/'analysis.ipynb').read_text())
                script='\n\n'.join(''.join(c['source']) for c in notebook['cells'] if c['cell_type']=='code')
                (Path(folder)/'notebook-run.py').write_text(script)
                execution=subprocess.run([sys.executable,'notebook-run.py'],cwd=folder,env=env,capture_output=True,text=True,timeout=45)
                self.assertEqual(execution.returncode,0,execution.stderr)
                self.assertTrue((Path(folder)/'visualization-1.html').exists())

    def test_exploratory_tampering_and_label_leakage_are_rejected(self):
        for sample,task in CASES[3:]:
            with self.subTest(task=task),tempfile.TemporaryDirectory() as folder:
                dataset,plan,path,_=prepared(folder,sample,task);result=unsupervised_result(path,plan)
                altered=copy.deepcopy(result);altered['projection']['x'][0]+=1
                with self.assertRaises(InputError):review_unsupervised(path,plan,altered)
                if task=='clustering':altered=copy.deepcopy(result);altered['silhouette']=1
                elif task=='pca':altered=copy.deepcopy(result);altered['variance_first_two']=1
                else:altered=copy.deepcopy(result);altered['scores'][0]+=1
                with self.assertRaises(InputError):review_unsupervised(path,plan,altered)
                if sample=='blobs':
                    with self.assertRaises(InputError):local_plan(dataset,{'question':'Find groups','task':'clustering','features':['known_group','measurement_a']})

    def test_supervised_candidate_selection_and_baselines_cannot_be_forged(self):
        with tempfile.TemporaryDirectory() as folder:
            _,plan,path,_=prepared(folder,'diabetes','regression');result=supervised_result(path,plan)
            altered=copy.deepcopy(result);altered['test']['baseline']=0
            with self.assertRaises(InputError):review_supervised(path,plan,altered)
            altered=copy.deepcopy(result);altered['candidates']['dummy']=0
            with self.assertRaises(InputError):review_supervised(path,plan,altered)

    def test_sealed_wrappers_reject_plan_or_result_mutation(self):
        good=wrapper('classification');self.assertEqual(validate_sealed_program(good,good),good)
        for bad in [good+'\nresult["test"]["mae"]=0',good.replace('result=supervised_result','plan.features=[]\nresult=supervised_result')]:
            with self.assertRaises(InputError):validate_sealed_program(bad,good)

    def test_every_new_task_crosses_interpreter_and_independent_review_boundaries(self):
        for sample,task in CASES:
            with self.subTest(task=task),tempfile.TemporaryDirectory() as folder:
                dataset,plan,path,_=prepared(folder,sample,task)
                result=(supervised_result if task in {'regression','classification'} else unsupervised_result)(path,plan)
                planner=Mock(return_value=SimpleNamespace(structured_output=plan))
                analyst=Mock(return_value=SimpleNamespace(structured_output=AnalystProgram(code=wrapper(task))))
                reviewer=Mock(return_value=SimpleNamespace(structured_output=AnalyticalReview(decision='accept',explanation='Checked calculations support a bounded analysis with the recorded limitations.',metrics=analytical_facts(result),limitations=['No causal interpretation is established.'])))
                interpreter=Mock();interpreter.cleanup_error=None;interpreter.execute.return_value={'results':[{'structuredContent':{'stdout':'VDS_RESULT='+json.dumps(result)}}]}
                report=run_forecast(dataset,path,{'question':plan.question},planner,analyst,reviewer,interpreter)
                self.assertTrue(report['trusted_review']['passed']);self.assertEqual(interpreter.execute.call_count,1)
                if task in {'clustering','pca','anomaly_detection'}:
                    reviewer.return_value.structured_output.limitations=['The 2D view uses at most 600 deterministically sampled rows.']
                    self.assertEqual(analytical_facts(result)['projection_preview_limit'],600)
                    self.assertTrue(run_forecast(dataset,path,{'question':plan.question},planner,analyst,reviewer,interpreter)['trusted_review']['passed'])
                reviewer.return_value.structured_output.metrics['rows']=-1
                with self.assertRaises(InputError):run_forecast(dataset,path,{'question':plan.question},planner,analyst,reviewer,interpreter)
                reviewer.return_value.structured_output.metrics=analytical_facts(result)
                reviewer.return_value.structured_output.explanation='This invented result has 87654321 groups.'
                with self.assertRaises(InputError):run_forecast(dataset,path,{'question':plan.question},planner,analyst,reviewer,interpreter)
                self.assertIn('without digits',json.loads(reviewer.call_args.args[0])['instruction'])

    def test_supported_large_classification_keeps_sandbox_and_figures_bounded(self):
        import numpy as np
        import pandas as pd
        from sklearn.datasets import make_classification
        x,y=make_classification(n_samples=20000,n_features=6,n_informative=4,random_state=42)
        frame=pd.DataFrame(x,columns=['m'+str(i) for i in range(6)])
        frame['outcome']=np.where(y==0,'eligible_for_standard_customer_service_'+'a'*60,'requires_enhanced_customer_assistance_'+'b'*60)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'dataset.parquet';frame.to_parquet(path,index=False)
            plan=SimpleNamespace(task='classification',metric='outcome',features=list(frame.columns[:-1]),dataset_version='a'*32,units='class')
            result=supervised_result(path,plan);enrich_result(result,plan)
            stdout='VDS_RESULT='+json.dumps(result)
            response={'content':[{'type':'text','text':stdout}],'structuredContent':{'stdout':stdout}}
            self.assertLess(len(json.dumps(response).encode()),2*1024*1024)
            self.assertLess(len(json.dumps(result).encode()),2*1024*1024)
            for visual in result['visuals']:
                for trace in visual['figure']['data']:self.assertLessEqual(len(trace['x']),1200)
            adjusted=copy.deepcopy(result);adjusted['classification_report']['macro avg']['precision']+=1e-15
            self.assertTrue(review_supervised(path,plan,adjusted)['passed'])

    def test_reviewed_catalog_matches_public_manifest_and_rejects_paths(self):
        root=Path(__file__).resolve().parents[1]
        self.assertEqual(json.loads((root/'static/dataset-catalog.json').read_text()),catalog())
        for sample in ['../../.env','https://example.com/data.csv','openml-999999']:
            with self.assertRaises(InputError):load(sample)
        with patch('analysis_engine.public_datasets._download',return_value=b'{"data_set_description":{"id":"62"}}'):
            with self.assertRaises(InputError):load('openml-61')
