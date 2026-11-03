"""A validated analytical brief. Models propose; deterministic checks authorize."""
from __future__ import annotations

import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from analysis_engine.ingestion import InputError

RELEASE = "tabular-local-v1"


class AnalysisPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_version: str
    revision: int = 1
    question: str = Field(min_length=1, max_length=2000)
    tier: Literal["quick", "deep"]
    task: Literal["monthly_summary", "forecast", "regression", "classification", "clustering", "pca", "anomaly_detection"]
    metric: str | None = Field(default=None,min_length=1,description="Exact name of the numeric measure or supervised target in profile.columns. Do not invent a field name.")
    clarification: str | None = Field(default=None,max_length=500,description="Only if a material business ambiguity prevents a safe plan; ask a natural business question, never request field mapping.")
    time_column: str | None = None
    features: list[str] = Field(default_factory=list, max_length=30)
    horizon: int = Field(default=3, ge=1, le=12)
    units: str = Field(default="source units (unconfirmed)", max_length=100)
    definition: str = Field(default="Sum of the selected measure; each row contributes once.", max_length=500)
    calendar: Literal["calendar_month"] = "calendar_month"
    validation: str = "none"
    methods: list[str] = Field(default_factory=list)
    max_seconds: int = Field(default=120, ge=1, le=300)
    max_candidates: int = Field(default=2, ge=1, le=5)
    research_requirement: Literal["none", "optional", "required"] = "none"
    reason: str = Field(max_length=500)
    planner: str = "local_rules"
    release: str = RELEASE


def check_plan(plan, dataset):
    columns = {c["name"]: c for c in dataset["profile"]["columns"]}
    if plan.dataset_version != dataset["id"]:
        raise InputError("Plan refers to an unauthorized dataset.")
    if plan.clarification:
        raise InputError(plan.clarification,"clarification_required")
    exploratory = plan.task in {"clustering", "pca", "anomaly_detection"}
    if exploratory:plan.metric=None;plan.time_column=None
    if not exploratory and plan.metric not in columns:
        raise InputError("I could not identify the requested business measure from the prepared data. What business outcome should the analysis describe?", "clarification_required")
    if plan.task in {"monthly_summary", "forecast", "regression"}:
        plan.units = columns[plan.metric].get("units") or "source units (unconfirmed)"
    if plan.task in {"monthly_summary", "forecast"}:
        if plan.time_column not in columns or columns[plan.time_column]["role"] != "time":
            raise InputError("Which business event should determine the timing of this analysis?", "clarification_required")
        if columns[plan.metric]["role"] != "measure":
            raise InputError("Which business outcome should this analysis describe?", "clarification_required")
    if plan.task in {"regression", "classification", "clustering", "pca", "anomaly_detection"}:
        if not plan.features or any(f not in columns for f in plan.features):
            raise InputError("What information would be available before the outcome you want to predict?", "clarification_required")
        teaching = dataset["profile"].get("teaching", {})
        forbidden = {plan.metric, teaching.get("target")} if not exploratory else {teaching.get("target") if teaching.get('task')!='forecast' else None}
        if any(f in forbidden for f in plan.features) or any(re.search(r"(^id$|_id$|final_|actual_|outcome|target|label|post_)", f, re.I) for f in plan.features):
            raise InputError("Predictors include identifiers, targets or possible post-outcome leakage.", "leakage_rejected")
        if exploratory and any(columns[f]['role'] != 'measure' for f in plan.features):
            raise InputError('Exploration requires at least two numeric measurements, excluding identifiers and outcomes.', 'readiness_failed')
        if exploratory and len(plan.features) < 2:
            raise InputError('Exploration needs at least two measurements.', 'readiness_failed')
        if not exploratory and plan.task == 'regression' and columns[plan.metric]['role'] != 'measure':
            raise InputError('The requested regression outcome is not numeric.', 'readiness_failed')
        if any(columns[f]['role'] in {'identifier', 'time', 'text'} for f in plan.features):
            raise InputError('Identifiers, timestamps and free text need a different validation contract.', 'readiness_failed')
        if not exploratory and any(columns[c]['role'] == 'time' for c in columns):
            raise InputError('This dataset has a time dimension. Explain a forecasting question or use independent observations; random-row prediction could leak future information.', 'clarification_required')
    expected_tier = "quick" if plan.task == "monthly_summary" else "deep"
    if plan.tier != expected_tier:
        raise InputError("Plan tier does not match the task.")
    if plan.task == "monthly_summary":
        plan.validation = "exact_aggregation"
        plan.methods = ["duckdb_monthly_sum"]
    elif plan.task == "forecast":
        plan.validation = "chronological_train_validation_test"
        plan.methods = ["naive", "holt", "linear_trend"]
        plan.max_candidates = 2
    elif plan.task in {'regression', 'classification'}:
        plan.methods = ['dummy', 'linear', 'tree']
        plan.validation = 'independent_rows_train_validation_test'
        plan.max_candidates = 2
    else:
        plan.methods = {'clustering': ['standard_scaler', 'kmeans', 'silhouette'], 'pca': ['standard_scaler', 'pca'], 'anomaly_detection': ['standard_scaler', 'isolation_forest']}[plan.task]
        plan.validation = 'exploratory_all_rows_no_predictive_holdout'
        plan.max_candidates = 5 if plan.task == 'clustering' else 1
    return plan


def local_plan(dataset, payload):
    question = str(payload.get("question", "")).strip()
    teaching = dataset['profile'].get('teaching', {})
    inferred = 'forecast' if re.search(r'forecast|predict.*month', question, re.I) else 'anomaly_detection' if re.search(r'anomal|outlier|unusual', question, re.I) else 'pca' if re.search(r'principal|\bpca\b|projection|reduce.*dimension', question, re.I) else 'clustering' if re.search(r'cluster|segment|groups', question, re.I) else teaching.get('task', 'monthly_summary')
    task = payload.get('task') or inferred
    exploratory = task in {'clustering', 'pca', 'anomaly_detection'}
    cols = dataset["profile"]["columns"]
    metric = payload.get("metric") or (None if exploratory else teaching.get("target"))
    time_column = payload.get("time_column")
    if not metric and not exploratory:
        exact = [c["name"] for c in cols if c["name"].lower() == "revenue"]
        measures = [c["name"] for c in cols if c["role"] == "measure"]
        metric = (exact or measures)[0] if len(exact or measures) == 1 else None
    if not metric and not exploratory:
        raise InputError("Which business outcome should this analysis describe?", "clarification_required")
    if not time_column:
        dates = [c["name"] for c in cols if c["role"] == "time"]
        time_column = dates[0] if len(dates) == 1 else None
    plan = AnalysisPlan(dataset_version=dataset["id"], question=question, tier="quick" if task == "monthly_summary" else "deep",
                        task=task, metric=metric, time_column=time_column, features=payload.get("features") or ([c["name"] for c in cols if c["name"] not in {metric, teaching.get("target") if teaching.get("task")!="forecast" else None} and c["role"] == "measure"][:30] if exploratory else teaching.get("features", [])),
                        horizon=payload.get("horizon", 3), units=str(payload.get("units") or "source units (unconfirmed)")[:100],
                        definition=str(payload.get("definition") or ("Predict the selected target for each independent row using pre-outcome features." if task in {"regression", "classification"} else "Sum of the selected measure; each row contributes once."))[:500],
                        validation="chronological_train_validation_test" if task == "forecast" else "train_validation_test" if task in {"regression", "classification"} else "exact_aggregation",
                        methods=["naive", "holt", "linear_trend"] if task == "forecast" else ["dummy", "linear", "tree"] if task in {"regression", "classification"} else ["duckdb_monthly_sum"],
                        reason="Explicit analysis controls and bounded local routing; no model call.")
    return check_plan(plan, dataset)



def compact_profile(profile):
    """Schema/quality facts suffice for routing; omit verbose provenance and previews."""
    return {'rows':profile['rows'],'columns':[{k:c[k] for k in ('name','role','type','missing','units','unique','min','max') if k in c} for c in profile['columns']],
            'duplicates':profile.get('duplicates',0),'preparation':profile.get('preparation'),
            'teaching':{k:v for k,v in profile.get('teaching',{}).items() if k in {'task','target','features','question','preparation'}}}

def strands_plan(dataset, payload, agent):
    """Caller supplies an approved Strands agent; schema contains no raw rows."""
    import json
    result = agent(json.dumps({"question": payload["question"], "dataset_version": dataset["id"],
                              "profile": compact_profile(dataset["profile"]), "controls": payload}), structured_output_model=AnalysisPlan)
    plan = result.structured_output
    if not isinstance(plan, AnalysisPlan):
        plan = AnalysisPlan.model_validate(plan)
    names = {c["name"].casefold():c["name"] for c in dataset["profile"]["columns"]}
    if plan.metric and plan.metric.casefold() in names:
        plan.metric = names[plan.metric.casefold()]
    if plan.time_column and plan.time_column.casefold() in names:
        plan.time_column = names[plan.time_column.casefold()]
    plan.features = [names.get(f.casefold(), f) for f in plan.features]
    dates = [c["name"] for c in dataset["profile"]["columns"] if c["role"] == "time"]
    if plan.time_column is None and len(dates) == 1 and plan.task in {"monthly_summary", "forecast"}:
        plan.time_column = dates[0]
    # Execution tier is a property of the supported task, not another model choice.
    plan.tier = 'quick' if plan.task == 'monthly_summary' else 'deep'
    plan.planner = "strands"
    return check_plan(plan, dataset)
