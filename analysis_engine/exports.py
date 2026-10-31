"""Curated, source-versioned reproduction bundles; never include uploaded data implicitly."""
from __future__ import annotations

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


def build_bundle(run, result):
    plan = run['plan']
    figures = [v['figure'] for v in result.get('visuals', [])]
    recipe = Path(__file__).with_name('tabular.py').read_text().replace('from analysis_engine.ingestion import InputError', 'from ingestion import InputError')
    analysis = """import json
from pathlib import Path
from types import SimpleNamespace
from vds_recipe import quick_result, forecast_result

plan = SimpleNamespace(**json.loads(Path('plan.json').read_text()))
recipe = forecast_result if plan.task == 'forecast' else quick_result
result = recipe('dataset.parquet', plan)
Path('reproduced-result.json').write_text(json.dumps(result, indent=2, allow_nan=False))
print(result['summary'])
"""
    plotting = """import json
from pathlib import Path
import plotly.graph_objects as go

figures = json.loads(Path('figures.json').read_text())
for i, figure in enumerate(figures, 1):
    go.Figure(figure).write_html(f'visualization-{i}.html', include_plotlyjs=True)
"""
    notebook = {'nbformat': 4, 'nbformat_minor': 5, 'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'}},
                'cells': [{'id': 'intro', 'cell_type': 'markdown', 'metadata': {}, 'source': ['# Reproduce this analysis\n', 'Provide your original prepared dataset as `dataset.parquet`. Source data is not included.']},
                          {'id': 'analysis', 'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [], 'source': analysis.splitlines(True)},
                          {'id': 'figures', 'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [], 'source': plotting.splitlines(True)}]}
    table = io.StringIO()
    writer = csv.writer(table, lineterminator='\n')
    writer.writerow(['month', 'value', 'kind'])
    for kind, key in [('observed', 'series'), ('forecast', 'forecast')]:
        for row in result.get(key, []):
            writer.writerow([row['month'], row['value'], kind])
    test_table = io.StringIO()
    test_writer = csv.writer(test_table, lineterminator='\n')
    test_writer.writerow(['month', 'actual', 'prediction', 'naive_baseline'])
    if result.get('test'):
        months = [r['month'] for r in result['series'][result['split']['validation_end']:]]
        test_writer.writerows(zip(months, result['test']['actual'], result['test']['predictions'], result['test']['baseline_predictions']))
    files = {'analysis.py': analysis, 'visualization.py': plotting, 'analysis.ipynb': json.dumps(notebook, indent=2),
             'plan.json': json.dumps(plan, indent=2), 'figures.json': json.dumps(figures, allow_nan=False),
             'result.json': json.dumps({k:v for k,v in result.items() if k!='sandbox'}, indent=2, allow_nan=False), 'series.csv': table.getvalue(), 'test-predictions.csv': test_table.getvalue(),
             'query.sql': result.get('sql', ''), 'vds_recipe.py': recipe,
             'ingestion.py': Path(__file__).with_name('ingestion.py').read_text(),
             'executed-wrapper.py': result.get('executed_code', analysis),
             'requirements.txt': '\n'.join(f'{k}=={v}' for k, v in result.get('versions', {}).items()) + '\nplotly==5.22.0\nopenpyxl==3.1.5\n',
             'README.md': '# Analysis reproduction\n\nSource data is excluded. Use your matching prepared `dataset.parquet` (see source hashes in result.json).\n'
                 + f'Executed analytical Python version: {result.get("python_version", "not recorded for this older run")}. Use a compatible Python environment for the pinned requirements.\n'
                 +
                 'Install requirements.txt in an isolated environment, then run `python analysis.py` and `python visualization.py`, or open analysis.ipynb.\n'
                 'The visualization code uses the exact saved figure data. Change layout.colorway to choose a palette.\n'
                 'The analysis includes all trusted support modules and the executed wrapper. Numerical and narrative checks remain in result.json.\n'
                 'For forecasting, chronological cutoffs, validation selection and the untouched test are preserved. No calibrated intervals or causal claims are implied.\n'}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    return buffer.getvalue()
