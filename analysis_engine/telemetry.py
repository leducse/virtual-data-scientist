"""Metadata-only operational events; analytical content stays in private evidence."""
import json
import logging
import os
import re
import time

logger = logging.getLogger('vds.telemetry')
logger.setLevel(logging.INFO)
ALLOWED = {'event', 'stage', 'status', 'attempt', 'duration_ms', 'run_id', 'sequence', 'error_code', 'input_tokens', 'output_tokens'}


def emit(**values):
    record = {key: value for key, value in values.items() if key in ALLOWED and isinstance(value, (str, int, float))}
    for key, value in tuple(record.items()):
        if isinstance(value, str) and not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', value):
            record.pop(key)
    record.update(service='vds', environment='development', release=os.environ.get('VDS_RELEASE', 'development'))
    metrics = []
    if record.get('stage') == 'analysis' and record.get('status') in {'completed', 'failed', 'cancelled'}:
        record['stage_events'] = 1
        metrics.append({'Name': 'stage_events', 'Unit': 'Count'})
    if record.get('stage') == 'analysis' and 'duration_ms' in record:
        metrics.append({'Name': 'duration_ms', 'Unit': 'Milliseconds'})
    if metrics:
        record['_aws'] = {'Timestamp': int(time.time() * 1000), 'CloudWatchMetrics': [
            {'Namespace': 'DecisionLayer/VDS', 'Dimensions': [['environment', 'stage', 'status']], 'Metrics': metrics}]}
    logger.info(json.dumps(record, allow_nan=False, separators=(',', ':')))
    return record


def safe_error(exc, run_id=None):
    emit(event='dependency_error', stage='runtime', status='failed', run_id=run_id or 'unknown',
         error_code=getattr(exc,'code',type(exc).__name__))
