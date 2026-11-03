"""Readable, task-specific reproduction code with exact inputs and checked outputs."""
from __future__ import annotations
import ast
import hashlib
import csv
import io
import json
import zipfile
from pathlib import Path

PALETTES={'decision':['#146659','#a66b16','#6d5f94','#346b96'], 'ocean':['#155f99','#008578','#b35b26','#78499a'],
          'plum':['#79417f','#b56a00','#147a72','#446da0'], 'accessible':['#0072b2','#d55e00','#009e73','#8b4b8a']}


def themed_bundle(data,palette):
    if palette not in PALETTES:raise ValueError('Unknown presentation palette')
    target=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as original,zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as output:
        for item in original.infolist():
            body=original.read(item.filename)
            if item.filename=='figures.json':
                figures=json.loads(body)
                for figure in figures:figure['layout']['colorway']=PALETTES[palette]
                body=json.dumps(figures,allow_nan=False).encode()
            output.writestr(item.filename,body)
        output.writestr('presentation.json',json.dumps({'palette':palette,'colors':PALETTES[palette],'note':'Presentation only; analytical evidence and numbers are unchanged.'}))
    return target.getvalue()


def _csv(header,rows):
    stream=io.StringIO();writer=csv.writer(stream,lineterminator='\n');writer.writerow(header);writer.writerows(rows);return stream.getvalue()


def build_bundle(run,result,recipe_source=None):
    plan=run['plan'];task=plan['task'];source=recipe_source or Path(__file__).with_name('tabular.py').read_text()
    recipe=source.replace('from analysis_engine.ingestion import InputError','from ingestion import InputError')
    functions={node.name:ast.get_source_segment(source,node) for node in ast.parse(source).body if isinstance(node,ast.FunctionDef)}
    if task=='monthly_summary':names=['quote','monthly_series','quick_result'];entry='quick_result';review=None
    elif task=='forecast':names=['versions','quote','monthly_series','mae','numeric_evidence_equal','fit_holt','forecast_values','forecast_result','review_forecast'];entry='forecast_result';review='review_forecast'
    elif task in {'regression','classification'}:names=['versions','numeric_evidence_equal','supervised_result','review_supervised'];entry='supervised_result';review='review_supervised'
    else:names=['versions','numeric_evidence_equal','exploratory_matrix','unsupervised_result','review_unsupervised'];entry='unsupervised_result';review='review_unsupervised'
    imports='''from __future__ import annotations
import hashlib
import importlib.metadata
import json
import math
import platform
import time
from pathlib import Path
from types import SimpleNamespace
from ingestion import InputError
'''
    imports+='\n# Fingerprint of the original executed recipe module; function bodies below are copied from it.\nRECIPE_SHA256='+repr(result.get('recipe_sha256','not-recorded'))+'\n'
    setup='''# Keep plan.json and the explicitly downloaded dataset.parquet beside this notebook/script.
plan=SimpleNamespace(**json.loads(Path('plan.json').read_text()))
original=json.loads(Path('result.json').read_text())
expected=original.get('evidence',{}).get('parquet_sha256')
if expected and hashlib.sha256(Path('dataset.parquet').read_bytes()).hexdigest()!=expected:
    raise ValueError('Prepared data hash differs from the recorded input.')
'''
    fit=f"# Fit the actual recipe: preprocessing, baselines, candidates and evaluation are visible above.\nresult={entry}('dataset.parquet',plan)\n"
    if review:fit+=f"result['review']={review}('dataset.parquet',plan,result)\n"
    checks='''# Compare recomputed outcomes to the saved evidence; this does not call the application or a model API.
if plan.task=='forecast':
    assert result['selected_method']==original['selected_method']
    assert math.isclose(result['test']['mae'],original['test']['mae'],rel_tol=1e-6,abs_tol=1e-6)
elif plan.task in {'regression','classification'}:
    metric=result['selection_metric']
    assert result['selected_method']==original['selected_method']
    assert math.isclose(result['test'][metric],original['test'][metric],rel_tol=1e-6,abs_tol=1e-6)
elif plan.task=='clustering':
    assert result['selected_k']==original['selected_k']
    assert math.isclose(result['silhouette'],original['silhouette'],rel_tol=1e-6,abs_tol=1e-6)
elif plan.task=='pca':
    assert math.isclose(result['variance_first_two'],original['variance_first_two'],rel_tol=1e-6,abs_tol=1e-6)
elif plan.task=='anomaly_detection':
    assert result['flags']==original['flags']
else:
    assert math.isclose(result['total'],original['total'],rel_tol=1e-8,abs_tol=1e-8)
Path('reproduced-result.json').write_text(json.dumps(result,indent=2,allow_nan=False))
print(result['summary'])
print('Saved evidence reproduced successfully.')
'''
    names=[name for name in names if name in functions]
    selected_source=[functions[name] for name in names]
    analysis='"""Reproduce the recorded '+task+' analysis. Includes the actual fitting and review code."""\n'+imports+'\n\n'+'\n\n'.join(selected_source)+'\n\n'+setup+fit+checks
    plotting='''# Figure recreation uses the exact saved, checked chart values.
import json
from pathlib import Path
import plotly.graph_objects as go

figures=json.loads(Path('figures.json').read_text())
for i,figure in enumerate(figures,1):
    chart=go.Figure(figure)
    chart.update_layout(template='plotly_white')
    chart.write_html(f'visualization-{i}.html',include_plotlyjs=True)
'''
    cells=[]
    def markdown(text):cells.append({'cell_type':'markdown','metadata':{},'source':text.splitlines(True)})
    def code(text):cells.append({'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':text.splitlines(True)})
    markdown('# Reproduce this '+task+' analysis\n\nDownload prepared data separately as `dataset.parquet`. Run all cells in this folder. This notebook contains the actual library imports, preprocessing, fitting and evaluation; figure-only downloads redraw saved values.\n\nAssumptions and the independent numerical/narrative reviews are retained in result.json. Model selection must not use the final test observations. Exploratory methods have no predictive holdout.\n')
    markdown('## Environment and fixed input');code(imports+setup)
    for name,body in zip(names,selected_source):markdown('## '+name.replace('_',' ').capitalize());code(body+'\n')
    markdown('## Fit and verify against the saved evidence');code(fit+checks)
    markdown('## Recreate the saved diagnostic figures');code(plotting)
    for i,cell in enumerate(cells):cell['id']='cell-'+str(i)
    notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},'cells':cells}
    figures=[v['figure'] for v in result.get('visuals',[])]
    files={'analysis.py':analysis,'analysis.ipynb':json.dumps(notebook,indent=2),'visualization.py':plotting,'plan.json':json.dumps(plan,indent=2),
           'figures.json':json.dumps(figures,allow_nan=False),'result.json':json.dumps({k:v for k,v in result.items() if k!='sandbox'},indent=2,allow_nan=False),
           'vds_recipe.py':recipe,'ingestion.py':Path(__file__).with_name('ingestion.py').read_text(),
           'executed-wrapper.py':result.get('executed_code',analysis),'query.sql':result.get('sql',''),
           'requirements.txt':'\n'.join(f'{k}=={v}' for k,v in result.get('versions',{}).items())+'\nplotly==5.22.0\nopenpyxl==3.1.5\n',
           'README.md':f'''# Reproduce the {task} analysis

1. Download "Prepared data (Parquet)" from this run and save it here as dataset.parquet. Source data is excluded by default.
2. Create an isolated Python environment and install requirements.txt. Recorded analytical Python: {result.get('python_version','not recorded for this older run')}.
3. Run `python analysis.py`, or run every cell in analysis.ipynb from this folder.
4. Run `python visualization.py` to recreate the saved figures as offline interactive HTML.

analysis.py and the notebook contain readable recipe source, including real library calls. vds_recipe.py preserves the complete support module, and executed-wrapper.py records what the hosted sandbox ran. ingestion.py is included; no application service is needed for reproduction. Recorded package versions come from the execution environment.

The code verifies the prepared-data hash when available and compares recomputed metrics to saved evidence. result.json retains the checks, selected plan, limitations and source hashes. Classification evidence uses compact integer class IDs when class_encoding is index_into_classes; the classes array maps IDs to names. CSV prediction tables decode the names. Row indices in CSV files are zero-based prepared-data positions; the interface displays one-based row numbers.

Supervised recipes assume independent observations and use training-only preprocessing, validation model selection, and held-out test evaluation. Forecasts use chronological cutoffs and have no calibrated intervals or seasonal component. Exploratory clustering, PCA and anomaly screening fit the observed dataset and imply no predictive accuracy or causation. Numeric reproduction tolerance is 1e-6 except the aggregation check (1e-8). Different package versions may change fitted results.
'''}
    if result.get('series'):
        files['series.csv']=_csv(['month','value','kind'],[(r['month'],r['value'],kind) for kind,key in [('observed','series'),('forecast','forecast')] for r in result.get(key,[])])
    if task=='forecast':
        months=[r['month'] for r in result['series'][result['split']['validation_end']:]]
        files['test-predictions.csv']=_csv(['month','actual','prediction','naive_baseline'],zip(months,result['test']['actual'],result['test']['predictions'],result['test']['baseline_predictions']))
    elif task in {'regression','classification'}:
        decode=lambda values:[result['classes'][v] for v in values] if result.get('class_encoding')=='index_into_classes' else values
        files['test-predictions.csv']=_csv(['row_index','actual','prediction','baseline'],zip(result['split']['test'],decode(result['test']['actual']),decode(result['test']['predictions']),decode(result['test']['baseline_predictions'])))
    elif task=='clustering':files['assignments.csv']=_csv(['row_index','cluster'],enumerate(result['labels']))
    elif task=='anomaly_detection':files['anomaly-scores.csv']=_csv(['row_index','score','flagged'],zip(range(result['rows']),result['scores'],result['flags']))
    if result.get('roc'):
        files['test-probabilities.csv']=_csv(['row_index','actual','prediction','positive_class','probability'],zip(result['split']['test'],decode(result['test']['actual']),decode(result['test']['predictions']),[result['roc']['positive_class']]*len(result['test']['actual']),result['test']['probabilities']))
        files['roc-curve.csv']=_csv(['false_positive_rate','true_positive_rate'],zip(result['roc']['fpr'],result['roc']['tpr']))
        files['precision-recall-curve.csv']=_csv(['recall','precision'],zip(result['precision_recall']['recall'],result['precision_recall']['precision']))
    if result.get('projection'):
        p=result['projection'];files['projection-sample.csv']=_csv(['row_index','PC1','PC2'],zip(p['row_indices'],p['x'],p['y']))
        files['loadings.csv']=_csv(['component',*result['features']],[(i+1,*row) for i,row in enumerate(p['components'])])
    if result.get('candidates'):files['candidate-comparison.csv']=_csv(['candidate','validation_metric'],[(key,value.get('validation_mae') if isinstance(value,dict) else value) for key,value in result['candidates'].items()])
    files['export-manifest.json']=json.dumps({'format_version':2,'task':task,'recipe_module_sha256':hashlib.sha256(recipe.encode()).hexdigest(),'source_data_included':False,'note':'Recipe source is preserved from the recorded bundle when upgrading a historical export.'},indent=2)
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,body in files.items():archive.writestr(name,body)
    return buffer.getvalue()
