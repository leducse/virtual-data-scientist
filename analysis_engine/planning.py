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
    task: Literal["monthly_summary", "forecast", "regression", "classification"]
    metric: str = Field(min_length=1,description="Exact name of the numeric measure or supervised target in profile.columns. Do not invent a field name.")
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
    max_candidates: int = Field(default=2, ge=1, le=2)
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
    if plan.metric not in columns:
        raise InputError("I could not identify the requested business measure from the prepared data. What business outcome should the analysis describe?", "clarification_required")
    if plan.task in {"monthly_summary", "forecast", "regression"}:
        plan.units = columns[plan.metric].get("units") or "source units (unconfirmed)"
    if plan.task in {"monthly_summary", "forecast"}:
        if plan.time_column not in columns or columns[plan.time_column]["role"] != "time":
            raise InputError("Which business event should determine the timing of this analysis?", "clarification_required")
        if columns[plan.metric]["role"] != "measure":
            raise InputError("Which business outcome should this analysis describe?", "clarification_required")
    if plan.task in {"regression", "classification"}:
        if not plan.features or any(f not in columns for f in plan.features):
            raise InputError("What information would be available before the outcome you want to predict?", "clarification_required")
        if plan.metric in plan.features or any(re.search(r"(^id$|_id$|final_|actual_|outcome|target|label|post_)", f, re.I) for f in plan.features):
            raise InputError("Predictors include identifiers, targets or possible post-outcome leakage.", "leakage_rejected")
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
    return plan


def local_plan(dataset, payload):
    question = str(payload.get("question", "")).strip()
    task = payload.get("task") or ("forecast" if re.search(r"forecast|predict.*month", question, re.I) else "monthly_summary")
    cols = dataset["profile"]["columns"]
    metric = payload.get("metric")
    time_column = payload.get("time_column")
    if not metric:
        exact = [c["name"] for c in cols if c["name"].lower() == "revenue"]
        measures = [c["name"] for c in cols if c["role"] == "measure"]
        metric = (exact or measures)[0] if len(exact or measures) == 1 else None
    if not metric:
        raise InputError("Which business outcome should this analysis describe?", "clarification_required")
    if not time_column:
        dates = [c["name"] for c in cols if c["role"] == "time"]
        time_column = dates[0] if len(dates) == 1 else None
    plan = AnalysisPlan(dataset_version=dataset["id"], question=question, tier="quick" if task == "monthly_summary" else "deep",
                        task=task, metric=metric, time_column=time_column, features=payload.get("features", []),
                        horizon=payload.get("horizon", 3), units=str(payload.get("units") or "source units (unconfirmed)")[:100],
                        definition=str(payload.get("definition") or ("Predict the selected target for each independent row using pre-outcome features." if task in {"regression", "classification"} else "Sum of the selected measure; each row contributes once."))[:500],
                        validation="chronological_train_validation_test" if task == "forecast" else "train_validation_test" if task in {"regression", "classification"} else "exact_aggregation",
                        methods=["naive", "holt", "linear_trend"] if task == "forecast" else ["dummy", "linear", "tree"] if task in {"regression", "classification"} else ["duckdb_monthly_sum"],
                        reason="Explicit analysis controls and bounded local routing; no model call.")
    return check_plan(plan, dataset)


def strands_plan(dataset, payload, agent):
    """Caller supplies an approved Strands agent; schema contains no raw rows."""
    import json
    result = agent(json.dumps({"question": payload["question"], "dataset_version": dataset["id"],
                              "profile": dataset["profile"], "controls": payload}), structured_output_model=AnalysisPlan)
    plan = result.structured_output
    if not isinstance(plan, AnalysisPlan):
        plan = AnalysisPlan.model_validate(plan)
    names = {c["name"].casefold():c["name"] for c in dataset["profile"]["columns"]}
    if plan.metric.casefold() in names:
        plan.metric = names[plan.metric.casefold()]
    if plan.time_column and plan.time_column.casefold() in names:
        plan.time_column = names[plan.time_column.casefold()]
    dates = [c["name"] for c in dataset["profile"]["columns"] if c["role"] == "time"]
    if plan.time_column is None and len(dates) == 1 and plan.task in {"monthly_summary", "forecast"}:
        plan.time_column = dates[0]
    # Execution tier is a property of the supported task, not another model choice.
    plan.tier = 'quick' if plan.task == 'monthly_summary' else 'deep'
    plan.planner = "strands"
    return check_plan(plan, dataset)
