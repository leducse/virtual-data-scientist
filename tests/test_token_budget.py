import unittest
from analysis_engine.token_budget import TokenBudget
from analysis_engine.ingestion import InputError

class TokenBudgetTests(unittest.TestCase):
    def test_internal_retries_share_the_same_budget_and_completed_turns_release_headroom(self):
        budget=TokenBudget(20000)
        request={'messages':[{'role':'user','content':[{'text':'Small question'}]}],'inferenceConfig':{'maxTokens':2500}}
        budget.before_call(request);first=budget.committed
        budget.before_call(request)
        self.assertEqual(budget.committed,2*first)
        with self.assertRaises(InputError):budget.before_call(request)
        budget.reconcile(0,1100)
        self.assertEqual(budget.committed,1100)
        budget.before_call(request);self.assertGreater(budget.committed,1100)

    def test_media_and_unreserved_usage_fail_closed(self):
        with self.assertRaises(InputError):TokenBudget(50000).before_call({'messages':[{'content':[{'image':{}}]}]})
        with self.assertRaises(InputError):TokenBudget(50000).reconcile(0,100)

    def test_missing_provider_usage_keeps_an_unknown_reservation_instead_of_counting_zero(self):
        from types import SimpleNamespace
        from unittest.mock import Mock,patch
        from analysis_engine.cloud_service import TrackedAgent
        usage=[]
        agent=Mock(return_value=SimpleNamespace(metrics=SimpleNamespace(accumulated_usage={})))
        agent.messages=[]
        with patch('strands.Agent',return_value=agent),patch('strands.models.BedrockModel'):
            tracked=TrackedAgent('planner','synthetic-model','us-east-1',usage)
            with self.assertRaises(InputError) as error:tracked('Question')
        self.assertEqual(error.exception.code,'outcome_unknown')
        self.assertTrue(usage[0]['unknown'])
