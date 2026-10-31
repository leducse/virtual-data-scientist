"""A killable local process for fixed recipes; this is not a security sandbox."""
from __future__ import annotations
import json
import resource
import sys
from pathlib import Path
from analysis_engine.planning import AnalysisPlan
from analysis_engine.ingestion import InputError
from analysis_engine.tabular import forecast_result, supervised_result


def main():
    input_path = Path(sys.argv[1])
    plan = AnalysisPlan.model_validate_json(input_path.read_text())
    resource.setrlimit(resource.RLIMIT_CPU, (plan.max_seconds, plan.max_seconds+1))
    def checkpoint(stage):
        tmp = input_path.parent / "stage.tmp"
        tmp.write_text(stage)
        tmp.replace(input_path.parent / "stage.txt")
    try:
        path = input_path.parent.parent / "dataset.parquet"
        function = forecast_result if plan.task == "forecast" else supervised_result
        result = function(path,plan,checkpoint)
    except Exception as exc:
        result = {"error": {"code": getattr(exc,"code","analysis_failed"), "message": str(exc) if isinstance(exc,InputError) else "The fixed recipe could not fit this dataset."}}
    tmp = input_path.parent / "output.tmp"
    tmp.write_text(json.dumps(result,allow_nan=False))
    tmp.replace(input_path.parent / "output.json")


if __name__ == "__main__":
    main()
