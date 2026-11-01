"""Reviewed public teaching snapshots and bounded, version-pinned OpenML imports."""
from __future__ import annotations
import hashlib
import io
import json
import time
import ssl
import certifi
import urllib.error
import urllib.request
from pathlib import Path
from analysis_engine.ingestion import InputError

ROOT = Path(__file__).with_name('sample_data')
OPENML = {
    'openml-61': {'id': '61', 'version': '1', 'file_id': '61', 'name': 'iris', 'licence': 'Public', 'task': 'classification', 'title': 'OpenML Iris', 'license': 'CC BY 4.0 (UCI Iris); OpenML labels it Public'},
    'openml-41517': {'id': '41517', 'version': '4', 'file_id': '21230546', 'name': 'Diabetes(scikit-learn)', 'licence': 'BSD (from scikit-learn)', 'task': 'regression', 'title': 'OpenML Diabetes', 'license': 'BSD (as attributed by OpenML to scikit-learn)'},
}


def catalog():
    items = json.loads((ROOT / 'catalog.json').read_text())
    for key, item in OPENML.items():
        items.append({'id': key, 'title': item['title'], 'task': item['task'], 'source': 'https://www.openml.org/d/' + item['id'],
                      'license': item['license'], 'version': item['version'], 'provider': 'OpenML', 'question':
                      'Which measurements help distinguish iris species?' if item['task'] == 'classification' else 'How accurately can the progression score be predicted?',
                      'synthetic': False, 'rows': 150 if item['id'] == '61' else 442, 'columns': 5 if item['id'] == '61' else 11})
    return items


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise InputError('The reviewed source redirected; import is paused until it is reviewed again.', 'dependency_failure')


def _download(path, maximum):
    # The origin and path are server-owned; no client URL is ever fetched.
    url = 'https://www.openml.org/' + path
    request = urllib.request.Request(url, headers={'User-Agent': 'DecisionLayerMLWorkbench/1', 'Accept': '*/*'})
    began = time.monotonic()
    try:
        with urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where()))).open(request, timeout=10) as response:
            chunks, size = [], 0
            while chunk := response.read(65536):
                size += len(chunk)
                if size > maximum or time.monotonic() - began > 15:
                    raise InputError('Public dataset exceeds the bounded import allowance.', 'upload_limit')
                chunks.append(chunk)
            return b''.join(chunks)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise InputError('The public dataset source is unavailable. Choose a bundled sample or try later.', 'dependency_failure') from exc


def load(sample_id):
    if not isinstance(sample_id, str) or len(sample_id) > 40:
        raise InputError('Choose a dataset from the reviewed gallery.')
    listed = next((d for d in catalog() if d['id'] == sample_id), None)
    if listed is None:raise InputError('That public dataset is not in the reviewed catalog.', 'not_found')
    if sample_id not in OPENML:
        raw = (ROOT / (sample_id + '.csv')).read_bytes()
        if hashlib.sha256(raw).hexdigest() != listed['sha256']:
            raise InputError('The teaching snapshot failed its integrity check.', 'dependency_failure')
        return raw, listed
    import pandas as pd
    from scipy.io import arff
    approved = OPENML[sample_id]
    metadata = json.loads(_download('api/v1/json/data/' + approved['id'], 200000))['data_set_description']
    if any(str(metadata.get(key)) != str(approved[key]) for key in ('id', 'version', 'file_id', 'name', 'licence')) or str(metadata.get('format', '')).lower() != 'arff':
        raise InputError('OpenML metadata changed; this snapshot needs review before import.', 'dependency_failure')
    raw = _download('data/v1/download/' + approved['file_id'], 2 * 1024 * 1024)
    try:
        data, _ = arff.loadarff(io.StringIO(raw.decode('utf-8')))
        frame = pd.DataFrame(data)
        if not 20 <= len(frame) <= 20000 or not 2 <= len(frame.columns) <= 31:
            raise ValueError('Unsupported dimensions')
        for column in frame.select_dtypes(include='object'):
            frame[column] = frame[column].map(lambda value: value.decode('utf-8') if isinstance(value, bytes) else value).replace('?', None)
        target = metadata['default_target_attribute']
        if target not in frame or ',' in target:raise ValueError('Unsupported target')
        csv = frame.to_csv(index=False, lineterminator='\n').encode()
        if len(csv) > 10 * 1024 * 1024:raise ValueError('Expanded data too large')
    except (ValueError, NotImplementedError, UnicodeError) as exc:
        raise InputError('This reviewed import is not a supported bounded tabular dataset.', 'readiness_failed') from exc
    listed.update(target=target, features=[c for c in frame if c != target], rows=len(frame), columns=len(frame.columns),
                  sha256=hashlib.sha256(csv).hexdigest(), upstream_sha256=hashlib.sha256(raw).hexdigest(),
                  preparation='Decoded the reviewed ARFF numeric/nominal columns to CSV; prepared through the normal ingestion path.')
    return csv, listed
