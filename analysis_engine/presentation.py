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
        'what': 'Smooths level and trend with gradual damping. This recipe selects among twelve fixed parameter settings using training error, then compares the fitted method on a separate validation period.',
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
    out = {'version': CATALOG_VERSION, 'suggestions': ml_recommendations(table,profile), 'notes': []}
    if len(dates) != 1 or measure is None:
        if not out['suggestions']:out['notes'].append('Describe the business outcome you want to understand so the analytical goal can be inferred.')
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
    if result.get('review',{}).get('passed') and result.get('task') in {'regression','classification','clustering','pca','anomaly_detection'}:
        return enrich_ml_result(result,plan)
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


for key,title,what,when,avoid,reference in [
    ('independent_validation','Independent-row validation','Fits preprocessing and candidates on training rows, chooses on validation rows and evaluates once on separate test rows.','Use when observations are independent and predictors are available before the outcome.','Repeated entities, time ordering and post-outcome predictors require a different split contract.','https://scikit-learn.org/stable/common_pitfalls.html'),
    ('supervised_models','Baseline, linear model and random forest','Compares a dummy baseline with Ridge/LogisticRegression and a bounded RandomForest through fitted preprocessing pipelines.','Use to assess numeric outcomes or recorded classes against a transparent baseline.','A better score does not establish causation or performance in another population.','https://scikit-learn.org/stable/supervised_learning.html'),
    ('classification_metrics','Classification diagnostics','Reports balanced accuracy, macro F1, per-class precision/recall and a confusion matrix on untouched test observations.','Use when errors across classes matter; binary probability outputs also provide ROC and precision–recall curves.','Small test sets have uncertain scores. A probability score is not automatically calibrated.','https://scikit-learn.org/stable/modules/model_evaluation.html'),
    ('regression_metrics','Regression diagnostics','Reports held-out MAE, RMSE, R-squared and residuals, alongside a training-only dummy baseline.','Use to inspect both average error and systematic over/under-prediction in source units.','R-squared can be negative. Random-row evaluation does not measure forecasting performance.','https://scikit-learn.org/stable/modules/model_evaluation.html#regression-metrics'),
    ('standard_scaler','Imputation and scaling','Fills missing numeric measurements with medians and standardizes their scales; supervised fits learn preprocessing on training rows only.','Use before distance-based clustering or PCA so different measurement units do not dominate.','Scaling changes interpretation; categorical measurements need a separate encoding contract.','https://scikit-learn.org/stable/modules/preprocessing.html'),
    ('kmeans','K-means segmentation','Fits bounded candidate group counts on standardized measurements and compares a deterministic sampled silhouette.','Use to explore approximately compact groups and their measurement profiles.','Curved or uneven-density groups can be poorly represented; these are not confirmed real-world categories.','https://scikit-learn.org/stable/modules/clustering.html#k-means'),
    ('silhouette','Silhouette comparison','Compares within-group and between-group distances; higher scores indicate better separation under that distance representation.','Use as one internal diagnostic for clustering candidate group counts.','It is neither predictive accuracy nor evidence of external validity or stability.','https://scikit-learn.org/stable/modules/generated/sklearn.metrics.silhouette_score.html'),
    ('pca','Principal component analysis','Projects median-imputed, standardized numeric measurements onto orthogonal directions of variation.','Use to explore correlated features, loadings and a lower-dimensional view.','A two-dimensional projection can hide information and does not predict a label. Component signs are arbitrary.','https://scikit-learn.org/stable/modules/decomposition.html#pca'),
    ('isolation_forest','Isolation Forest anomaly screening','Fits randomized isolation trees; observations with larger negative sample scores are more unusual under this model.','Use to prioritize unusual measurement combinations for investigation.','Automatic threshold flags are not confirmed errors or calibrated probabilities. No ground-truth accuracy is implied.','https://scikit-learn.org/stable/modules/outlier_detection.html#isolation-forest')]:
    METHODS[key]={'title':title,'what':what,'when':when,'avoid':avoid,'reference':reference,
                  'example':'The figures use this run’s checked observations and metrics; no illustrative value is substituted for your result.',
                  'checks':'Source rows, preprocessing/splits and numerical diagnostics are verified before publication. Exploratory and predictive results have different validation contracts.'}


def ml_recommendations(table,profile):
    teaching=profile.get('teaching',{})
    cols=profile['columns'];target=teaching.get('target')
    out=[]
    if teaching.get('task') in {'classification','regression'} and profile['rows']>=60:
        out.append({'id':teaching['task'],'question':teaching['question'],
                    'why':'The reviewed teaching metadata identifies the outcome and pre-outcome measurements. Preprocessing, baseline and candidate selection use separate training/validation/test rows.',
                    'effort':'Fit and evaluate models','methods':learning(['independent_validation','supervised_models','classification_metrics' if teaching['task']=='classification' else 'regression_metrics'])})
    elif not any(c['role']=='time' for c in cols):
        targets=[c for c in cols if re.search(r'^(target|outcome|label|diagnosis|species|cultivar|progression|class)$',c['name'],re.I) and not c['missing']]
        if len(targets)==1 and profile['rows']>=60:
            target=targets[0]['name'];values=table[target].to_pylist();classes=len(set(values))
            task='classification' if 2<=classes<=10 else 'regression' if targets[0]['role']=='measure' else None
            if task:out.append({'id':task,'question':f'How well can the recorded {target} be predicted from the other pre-outcome measurements?',
                                'why':'The profile identifies a plausible recorded outcome. The agent will check available predictors and explain independent-row assumptions.',
                                'effort':'Fit and evaluate models','methods':learning(['independent_validation','supervised_models'])})
    excluded=target if teaching.get('task')!='forecast' else None
    measurements=[c for c in cols if c['role']=='measure' and c['name']!=excluded and not re.search(r'(^id$|_id$|target|label|known_group)',c['name'],re.I)]
    if len(measurements)>=2 and profile['rows']>=20:
        for key,question,why,methods in [
            ('clustering','What groups appear in the numeric measurements?','Explore scaled measurement groups and compare their separation.',['standard_scaler','kmeans','silhouette']),
            ('pca','Show a principal component view of the numeric measurements','Explore variation and loadings without treating the projection as a prediction.',['standard_scaler','pca']),
            ('anomaly_detection','Which rows have unusual combinations of numeric measurements?','Prioritize unusual observations for investigation; flags are not confirmed errors.',['standard_scaler','isolation_forest'])]:
            out.append({'id':key,'question':question,'why':why,'effort':'Exploratory analysis','methods':learning(methods)})
    return out


def enrich_ml_result(result,plan):
    import numpy as np
    visuals=[]
    def add(key,title,purpose,traces,xlabel,ylabel,split='exploratory'):
        visuals.append({'id':key,'title':title,'purpose':purpose,'split':split,'dataset_version':plan.dataset_version,
                        'figure':{'data':traces,'layout':{'xaxis':{'title':xlabel},'yaxis':{'title':ylabel}}}})
    def scatter(name,x,y):return {'type':'scatter','mode':'markers','name':name,'x':list(x),'y':list(y)}
    def bar(name,x,y):return {'type':'bar','name':name,'x':list(x),'y':list(y)}
    task=result['task']
    if task in {'regression','classification'}:
        candidates=result['candidates'];metric=result['selection_metric']
        add('model-selection','Validation model comparison',f'{"Higher" if task=="classification" else "Lower"} {metric} is better. Final test observations were not used for model selection.',
            [bar(metric,list(candidates),list(candidates.values()))],'Candidate','Validation '+metric,'validation')
        test=result['test']
        if task=='regression':
            actual,pred=test['actual'],test['predictions'];n=min(len(actual),600)
            add('predictions','Actual and predicted outcomes',f'Untouched test rows; showing {n} of {len(actual)} observations.',[scatter('Test predictions',actual[:n],pred[:n])],'Actual outcome','Predicted outcome','test')
            add('residuals','Residuals against predictions','Residual = actual minus prediction. Look for systematic patterns rather than relying only on the average score.',[scatter('Residual',pred[:n],test['residuals'][:n])],'Predicted outcome','Residual','test')
        else:
            labels=result['classes']
            add('confusion','Confusion matrix','Rows are actual classes; columns are predicted classes on untouched test observations.',
                [{'type':'heatmap','name':'Count','x':labels,'y':labels,'z':result['confusion_matrix']}],'Predicted class','Actual class','test')
            add('per-class','Per-class precision and recall','Scores are calculated from the same final test predictions.',
                [bar(name,labels,[row[key] for row in result['per_class']]) for name,key in [('Precision','precision'),('Recall','recall')]],'Class','Score','test')
            if result.get('roc'):
                roc=result['roc'];pr=result['precision_recall']
                ri=np.linspace(0,len(roc['fpr'])-1,min(1000,len(roc['fpr'])),dtype=int)
                pi=np.linspace(0,len(pr['recall'])-1,min(1000,len(pr['recall'])),dtype=int)
                add('roc','Binary ROC curve','Positive class: '+roc['positive_class']+'. Up to 1,000 curve points are displayed; complete values remain in the evidence/downloads. Probabilities are not automatically calibrated.',
                    [{'type':'scatter','mode':'lines','name':'ROC','x':[roc['fpr'][i] for i in ri],'y':[roc['tpr'][i] for i in ri]}],'False positive rate','True positive rate','test')
                add('precision-recall','Binary precision–recall curve','Up to 1,000 curve points are displayed; full values remain in downloads. The test set is not used to tune a deployment threshold.',
                    [{'type':'scatter','mode':'lines','name':'Precision / recall','x':[pr['recall'][i] for i in pi],'y':[pr['precision'][i] for i in pi]}],'Recall','Precision','test')
        methods=['independent_validation','supervised_models','classification_metrics' if task=='classification' else 'regression_metrics']
    else:
        p=result['projection'];ids=p['row_indices'];x=p['x'];y=p['y']
        if task=='clustering':
            labels=result['labels'];traces=[scatter('Group '+str(k+1),[x[j] for j,i in enumerate(ids) if labels[i]==k],[y[j] for j,i in enumerate(ids) if labels[i]==k]) for k in range(result['selected_k'])]
            add('clusters','Groups in a principal component view','Up to 600 sampled rows; labels were fitted using all selected standardized measurements, not just the two displayed components.',traces,'PC1','PC2')
            add('cluster-sizes','Group sizes','Complete-dataset assignment counts.',[bar('Rows',list(result['cluster_counts']),list(result['cluster_counts'].values()))],'Group','Rows')
            add('cluster-selection','Cluster-count comparison','Higher sampled silhouette is better; no predictive accuracy or external group validity is implied.',[bar('Silhouette',list(result['candidates']),list(result['candidates'].values()))],'Number of groups','Silhouette')
            methods=['standard_scaler','kmeans','silhouette','pca']
        elif task=='pca':
            add('projection','Principal component view','Up to 600 sampled observations. The first two components may omit meaningful variation.',[scatter('Observations',x,y)],'PC1','PC2')
            names=['PC'+str(i+1) for i in range(len(p['explained_variance_ratio']))]
            add('variance','Explained variance by component','Fractions refer to variance after imputation and standard scaling. At most ten components are displayed.',[bar('Variance fraction',names,p['explained_variance_ratio'])],'Component','Variance fraction')
            add('loadings','Principal component loadings','Signed standardized-feature weights; component signs can flip without changing the projection.',[{'type':'heatmap','name':'Loading','x':result['features'],'y':names,'z':p['components']}],'Measurement','Component')
            methods=['standard_scaler','pca']
        else:
            flags=result['flags'];traces=[scatter(name,[x[j] for j,i in enumerate(ids) if flags[i]==flag],[y[j] for j,i in enumerate(ids) if flags[i]==flag]) for flag,name in [(0,'Other observations'),(1,'Flagged for investigation')]]
            add('anomalies','Unusual observations in a component view','Up to 600 sampled rows. Flags come from Isolation Forest on all selected measurements; this projection is only a view.',traces,'PC1','PC2')
            hist=result['score_histogram'];centers=[(a+b)/2 for a,b in zip(hist['edges'],hist['edges'][1:])]
            add('anomaly-scores','Distribution of anomaly scores','Larger scores indicate more unusual observations under this model; scores are not probabilities.',[bar('Rows',centers,hist['counts'])],'Negative sample score','Rows')
            add('ranked-anomalies','Highest anomaly scores','One-based prepared-data row positions. Investigate these observations; they are not confirmed errors.',[bar('Score',['Row '+str(i+1) for i in result['top_rows']],[result['scores'][i] for i in result['top_rows']])],'Prepared row','Score')
            methods=['standard_scaler','isolation_forest','pca']
    result['visuals']=visuals;result['methodology']=learning(methods);result['presentation_version']=CATALOG_VERSION
    return result
