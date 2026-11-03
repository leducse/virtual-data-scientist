import unittest
from analysis_engine.code_policy import validate_forecast_program
from analysis_engine.ingestion import InputError

GOOD='''import json
from types import SimpleNamespace
from vds_recipe import forecast_result
with open("plan.json") as f:
    plan=SimpleNamespace(**json.load(f))
result=forecast_result("dataset.parquet",plan)
print("VDS_RESULT="+json.dumps(result))
'''


class CodePolicyTests(unittest.TestCase):
    def test_approved_wrapper_and_aliases(self):
        self.assertEqual(validate_forecast_program(GOOD),GOOD)
        self.assertTrue(validate_forecast_program(GOOD.replace('import json','import json as j').replace('json.','j.')))
    def test_network_filesystem_introspection_and_unsupported_execution_rejected(self):
        for bad in ['import os\nos.system("echo bad")','import boto3\nboto3.client("s3")','open("/etc/passwd")','eval("1")','x.__class__.__base__','while True: pass',GOOD.replace('"dataset.parquet"','"other.parquet"'),GOOD+'\nresult.clear()',GOOD+'\njson=SimpleNamespace(dumps=open)',GOOD+'\nprint(__builtins__)']:
            with self.subTest(code=bad),self.assertRaises(InputError):validate_forecast_program(bad)


if __name__=='__main__':unittest.main()
