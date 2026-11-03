"""Re-run a saved fixed recipe after checking its code and immutable input hashes."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analysis_engine.planning import AnalysisPlan
from analysis_engine.tabular import RECIPE_SHA256, quick_result, forecast_result, supervised_result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence',type=Path)
    parser.add_argument('parquet',type=Path)
    args=parser.parse_args()
    run=json.loads(args.evidence.read_text())
    evidence=run['result']['evidence']
    if evidence['recipe_sha256'] != RECIPE_SHA256:
        parser.error('Check out the saved recipe version before reproducing; saved Python is never executed automatically.')
    if hashlib.sha256(args.parquet.read_bytes()).hexdigest()!=evidence['parquet_sha256']:
        parser.error('Parquet hash does not match the saved input version.')
    plan=AnalysisPlan.model_validate(evidence['plan'])
    function=quick_result if plan.tier=='quick' else forecast_result if plan.task=='forecast' else supervised_result
    print(json.dumps(function(args.parquet,plan),allow_nan=False,indent=2))


if __name__=='__main__':main()
