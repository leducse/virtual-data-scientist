"""Reviewed teaching copy and figures derived only from checked analytical facts."""
from __future__ import annotations

import copy
import datetime as dt
import re

CATALOG_VERSION = '2026-10-31.1'
METHODS = {
    'monthly_sum': {
        'title': 'Monthly aggregation',
        'what': 'Adds the selected business measure within each calendar month to describe historical activity.',
        'when': 'Use for additive amounts such as revenue, costs or units sold when each row contributes once.',
        'avoid': 'Do not sum percentages, prices, averages or account balances without a suitable business definition.',
        'example': 'Illustrative example: two sales of $40 and $60 in January give a January total of $100.',
        'checks': 'The total is recomputed independently from the prepared source. Missing selected dates or amounts stop publication.',
        'reference': 'https://duckdb.org/docs/stable/sql/functions/aggregates.html',
    },
    'naive': {
        'title': 'Naive forecast',
        'what': 'Uses the last observed monthly value for each future month.',
        'when': 'Use as a transparent persistence baseline; more complex models should earn their place against it.',
        'avoid': 'It does not model a trend, seasonality or a change in business conditions.',
        'example': 'Illustrative example: if the latest month was $100, the next three predictions are each $100.',
        'checks': 'Compare forecast error on exactly the same held-out months as competing models.',
        'reference': 'https://otexts.com/fpp3/simple-methods.html',
    },
    'holt': {
        'title': 'Damped Holt trend',
        'what': 'Smooths the level and trend, gradually reducing the extrapolated trend farther into the future.',
        'when': 'Consider when a regularly spaced monthly history has a changing level and a trend.',
        'avoid': 'This recipe has no seasonal component. Structural changes or a short history can make extrapolation unreliable.',
        'example': 'Illustrative example: recent steady growth can continue, with smaller trend contributions farther ahead.',
        'checks': 'Fit only earlier months, compare validation MAE, and assess the chosen method on a later untouched test window.',
        'reference': 'https://www.statsmodels.org/stable/generated/statsmodels.tsa.holtwinters.Holt.html',
    },
    'linear_trend': {
        'title': 'Linear trend',
        'what': 'Fits a straight line to the measure over time and extends that line.',
        'when': 'Consider for an approximately steady increase or decrease over the observed period.',
        'avoid': 'A straight line can miss seasonality, turning points and limits on growth. It does not explain causes.',
        'example': 'Illustrative example: a fitted increase of $10 per month extends that change into each future month.',
        'checks': 'Select on earlier validation observations; report performance on the separate final test observations.',
        'reference': 'https://numpy.org/doc/stable/reference/generated/numpy.polyfit.html',
    },
    'chronological_validation': {
        'title': 'Chronological validation and test',
        'what': 'Uses earlier months to fit, the next months to choose a method, and the final months to evaluate it.',
        'when': 'Use for forecasts where future information must not influence a prediction of the past.',
        'avoid': 'Do not use the final test error to keep selecting models. A single holdout does not establish performance across all seasons.',
        'example': 'Illustrative example: train on months 1–18, select on 19–21 and test on 22–24. Actual cutoffs depend on this run.',
        'checks': 'Source dates, non-overlapping cutoffs and trusted model refits are checked independently.',
        'reference': 'https://otexts.com/fpp3/tscv.html',
    },
    'mae': {
        'title': 'Mean absolute error (MAE)',
        'what': 'The average distance between actual values and predictions, in the original measure’s units.',
        'when': 'Use to compare prediction errors on the same observations. Smaller is better.',
        'avoid': 'MAE is not a percentage or a probability. Comparing unrelated datasets with different scales is misleading.',
        'example': 'Illustrative example: errors of $10 and $30 have an MAE of $20.',
        'checks': 'MAE is recomputed from the actual and predicted values, including the naive baseline.',
        'reference': 'https://otexts.com/fpp3/accuracy.html',
    },
}


def learning(method_ids):
    return [dict(id=key, version=CATALOG_VERSION, **copy.deepcopy(METHODS[key])) for key in method_ids if key in METHODS]


def recommendations(table, profile):
    """No model call or automatic fitting; technical mappings stay on the server."""
    dates = [c for c in profile['columns'] if c['role'] == 'time']
    measures = [c for c in profile['columns'] if c['role'] == 'measure']
    preferred = [c for c in measures if re.search(r'revenue|sales|amount|cost|quantity|units', c['name'], re.I)]
    measure = preferred[0] if len(preferred) == 1 else measures[0] if len(measures) == 1 else None
    out = {'version': CATALOG_VERSION, 'suggestions': [], 'notes': []}
    if len(dates) != 1 or measure is None:
        out['notes'].append('Ask which business outcome and time period you want to understand; several interpretations may be possible.')
        return out
    date = dates[0]
    if date['missing'] or measure['missing']:
        out['notes'].append('Some relevant dates or values are missing. Resolve them before a monthly summary or forecast.')
        return out
    if measure.get('units') == '%' or re.search(r'rate|percent|average|balance|price', measure['name'], re.I):
        out['notes'].append('This measure may not be additive. Explain the business question so its aggregation can be checked.')
        return out
    months = sorted({str(value)[:7] for value in table[date['name']].to_pylist()})
    count = len(months)
    if not count or count > 1200:
        out['notes'].append('Monthly analysis needs between one and 1,200 observed months.')
        return out
    if profile.get('duplicates'):
        out['notes'].append('Repeated rows were detected. Confirm they represent separate activity before interpreting totals.')
    name = measure['name']
    out['suggestions'].append({'id': 'monthly_summary', 'question': f'How has monthly {name} changed?',
        'why': f'A date and an additive-looking measure cover {count} observed months. Each source row contributes once.',
        'effort': 'Fast summary', 'methods': learning(['monthly_sum'])})
    first, last = [dt.date.fromisoformat(value + '-01') for value in (months[0], months[-1])]
    span = (last.year - first.year) * 12 + last.month - first.month + 1
    if count >= 12 and count == span and not profile.get('duplicates'):
        out['suggestions'].append({'id': 'forecast', 'question': f'Forecast monthly {name} for the next three months',
            'why': f'{count} consecutive months support a bounded trend comparison and held-out evaluation. The final month is assumed complete.',
            'effort': 'Deeper analysis', 'methods': learning(['naive', 'holt', 'linear_trend', 'chronological_validation', 'mae'])})
    else:
        out['notes'].append('Forecast suggestions need at least 12 consecutive months and resolved duplicate-row concerns. Missing months are not filled automatically.')
    return out


def enrich_result(result, plan):
    """Never generate browser code or statistical claims from unvalidated prose."""
    if not result.get('review', {}).get('passed') or not result.get('series'):
        return result
    rows = result['series']
    units = plan.units
    def figure(key, title, purpose, traces, split='observed'):
        return {'id': key, 'title': title, 'purpose': purpose, 'split': split,
                'dataset_version': plan.dataset_version, 'units': units,
                'figure': {'data': traces, 'layout': {'xaxis': {'title': 'Month', 'type': 'category'},
                                                   'yaxis': {'title': units}, 'hovermode': 'x unified'}}}
    def line(name, source, dash=None):
        trace = {'type': 'scatter', 'mode': 'lines+markers', 'name': name,
                 'x': [r['month'] for r in source], 'y': [r['value'] for r in source]}
        if dash:
            trace['line'] = {'dash': dash}
        return trace
    traces = [line('Observed', rows)]
    if result.get('forecast'):
        traces.append(line('Forecast', [rows[-1], *result['forecast']], 'dash'))
    visuals = [figure('history', 'History and forecast' if result.get('forecast') else 'Monthly history',
                      'See the observed business measure over time. Forecasts have no calibrated interval.', traces)]
    method_ids = ['monthly_sum']
    if result['task'] == 'forecast':
        start = result['split']['validation_end']
        months = [r['month'] for r in rows[start:]]
        test = result['test']
        visuals.append(figure('holdout', 'Predictions on untouched test months',
            'Compare actuals with predictions made using only earlier observations.',
            [{'type': 'scatter', 'mode': 'lines+markers', 'name': name, 'x': months, 'y': test[key]}
             for name, key in [('Actual', 'actual'), ('Selected model', 'predictions'), ('Naive baseline', 'baseline_predictions')]], 'test'))
        candidate_names = list(result['candidates'])
        comparison = figure('validation', 'How the method was selected',
            'Lower validation MAE is better. Final test results were not used for selection.',
            [{'type': 'bar', 'name': 'Validation MAE', 'x': candidate_names,
              'y': [result['candidates'][name]['validation_mae'] for name in candidate_names]}], 'validation')
        comparison['figure']['layout']['xaxis']['title'] = 'Candidate method'
        comparison['figure']['layout']['yaxis']['title'] = f'MAE ({units})'
        visuals.append(comparison)
        method_ids.extend(['naive', 'holt', 'linear_trend', 'chronological_validation', 'mae'])
    result['visuals'] = visuals
    result['methodology'] = learning(method_ids)
    for item in result['methodology']:
        if item['id'] in result.get('candidates', {}):
            item['disposition'] = 'Selected on validation MAE' if item['id'] == result.get('selected_method') else 'Compared on validation MAE; not selected'
    result['presentation_version'] = CATALOG_VERSION
    return result
