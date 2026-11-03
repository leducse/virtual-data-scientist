import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from analysis_engine.agent_workflow import run_forecast,AnalystProgram,ReviewDecision
from analysis_engine.ingestion import parse_table,write_parquet,InputError
from analysis_engine.planning import local_plan
from analysis_engine.tabular import forecast_result
from test_code_policy import GOOD


class AgentWorkflowTests(unittest.TestCase):
    def test_join_checked_execution_before_independent_review(self):
        with tempfile.TemporaryDirectory() as folder:
            table,profile=parse_table('sales.csv',(Path(__file__).parent/'fixtures/monthly_revenue.csv').read_bytes())
            path=Path(folder)/'dataset.parquet';write_parquet(table,path)
            dataset={'id':'dataset-1','profile':profile}
            payload={'question':'Forecast the next three months','task':'forecast','metric':'revenue','time_column':'date'}
            plan=local_plan(dataset,payload)
            result=forecast_result(path,plan)
            planner=Mock(return_value=SimpleNamespace(structured_output=plan))
            analyst=Mock(return_value=SimpleNamespace(structured_output=AnalystProgram(code=GOOD)))
            reviewer=Mock(return_value=SimpleNamespace(structured_output=ReviewDecision(decision='accept',explanation='The checked trend forecast has limited seasonal coverage.',test_mae=result['test']['mae'],baseline_mae=result['test']['baseline_mae'],limitations=['No calibrated uncertainty interval.'])))
            interpreter=Mock();interpreter.cleanup_error=None;interpreter.execute.return_value={'results':[{'structuredContent':{'stdout':'VDS_RESULT='+json.dumps(result)}}]}
            report=run_forecast(dataset,path,payload,planner,analyst,reviewer,interpreter)
            self.assertTrue(report['trusted_review']['passed'])
            analyst.side_effect=[SimpleNamespace(structured_output=AnalystProgram(code='def main(): pass')),SimpleNamespace(structured_output=AnalystProgram(code=GOOD))]
            repaired=run_forecast(dataset,path,payload,planner,analyst,reviewer,interpreter)
            self.assertEqual(repaired['limits']['analyst_attempts'],2)
            analyst.side_effect=None
            self.assertEqual(report['limits']['agent_invocations'],3)
            self.assertEqual(interpreter.execute.call_args.args[1],GOOD)
            self.assertFalse(report['cloud_verified'])
            reviewer.return_value=SimpleNamespace(structured_output=ReviewDecision(decision="accept",explanation="Test MAE 304.17 versus baseline 860; forecast spans 3 months.",test_mae=round(result["test"]["mae"],2),baseline_mae=860,limitations=[]))
            self.assertTrue(run_forecast(dataset,path,payload,planner,analyst,reviewer,interpreter)["trusted_review"]["passed"])
            reviewer.return_value=SimpleNamespace(structured_output=ReviewDecision(decision="accept",explanation="Accuracy is 99 percent.",test_mae=result["test"]["mae"],baseline_mae=860,limitations=[]))
            with self.assertRaises(InputError):run_forecast(dataset,path,payload,planner,analyst,reviewer,interpreter)
            # Planted future-information predictions + matching fake metrics still fail a trusted refit.
            wrong=copy.deepcopy(result)
            wrong['test']['predictions']=wrong['test']['actual']
            wrong['test']['mae']=0
            interpreter.execute.return_value={'results':[{'structuredContent':{'stdout':'VDS_RESULT='+json.dumps(wrong)}}]}
            reviewer.reset_mock()
            with self.assertRaises(InputError):run_forecast(dataset,path,payload,planner,analyst,reviewer,interpreter)
            reviewer.assert_not_called()
            interpreter.execute.return_value={'results':[{'structuredContent':{'stdout':'VDS_RESULT='+json.dumps(result)}}]}
            reviewer.return_value=SimpleNamespace(structured_output=ReviewDecision(decision='accept',explanation='Supported.',test_mae=0,baseline_mae=0,limitations=[]))
            with self.assertRaises(InputError) as e:run_forecast(dataset,path,payload,planner,analyst,reviewer,interpreter)
            self.assertEqual(e.exception.code,'review_rejected')


if __name__=='__main__':unittest.main()
