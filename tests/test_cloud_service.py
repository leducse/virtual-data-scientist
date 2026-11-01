import base64
import json
import threading
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
from moto import mock_aws
import boto3
from analysis_engine.cloud_service import CloudService
from analysis_engine.cloud_store import CloudStore
from analysis_engine.planning import local_plan
from analysis_engine.ingestion import InputError


@mock_aws
class CloudServiceTests(unittest.TestCase):
    def setUp(self):
        s3=boto3.client('s3',region_name='us-east-1');s3.create_bucket(Bucket='vds-service-test')
        table=boto3.resource('dynamodb',region_name='us-east-1').create_table(TableName='state',KeySchema=[{'AttributeName':'pk','KeyType':'HASH'},{'AttributeName':'sk','KeyType':'RANGE'}],AttributeDefinitions=[{'AttributeName':'pk','AttributeType':'S'},{'AttributeName':'sk','AttributeType':'S'}],BillingMode='PAY_PER_REQUEST')
        self.service=CloudService(store=CloudStore(s3,table,'vds-service-test'),region='us-east-1')
        self.owner='a'*64
    def tearDown(self):self.service.pool.shutdown(wait=True)
    def test_overlapping_upload_preparation_does_not_duplicate_or_remove_source(self):
        upload_id='9'*32
        self.service.store.put_blob(self.owner,'incoming/'+upload_id,(Path(__file__).parent/'fixtures/monthly_revenue.csv').read_bytes())
        entered=threading.Event();release=threading.Event()
        original=self.service.store.put_blob
        def paused(*args,**kwargs):
            entered.set()
            if not release.wait(5):raise RuntimeError('Test upload did not resume')
            return original(*args,**kwargs)
        payload={'upload_id':upload_id,'name':'sales.csv'}
        with patch.object(self.service.store,'put_blob',side_effect=paused):
            future=self.service.pool.submit(self.service.prepare_upload,self.owner,payload)
            self.assertTrue(entered.wait(5))
            try:
                with self.assertRaises(InputError) as error:self.service.prepare_upload(self.owner,payload)
                self.assertEqual(error.exception.code,'capacity_exceeded')
                self.assertTrue(self.service.store.blob(self.owner,'incoming/'+upload_id))
            finally:release.set()
            dataset=future.result(timeout=10)
        self.assertEqual(self.service.prepare_upload(self.owner,payload)['id'],dataset['id'])
        self.assertEqual(len(self.service.store.items(self.owner,'dataset')),1)
    def test_teaching_snapshot_is_idempotent_owner_scoped_and_uses_no_analysis_credit(self):
        before=self.service.quotas.status({'owner':self.owner,'kind':'member'})
        dataset=self.service.load_sample(self.owner,'iris')
        self.assertEqual(dataset['profile']['teaching']['target'],'species')
        self.assertEqual(self.service.load_sample(self.owner,'iris')['id'],dataset['id'])
        self.assertEqual(self.service.quotas.status({'owner':self.owner,'kind':'member'}),before)
        self.assertGreaterEqual(len(dataset['experience']['suggestions']),4)
        with self.assertRaises(InputError):self.service.store.dataset('b'*64,dataset['id'])
        with self.assertRaises(InputError):self.service.load_sample(self.owner,'../../.env')

    def test_automatic_cloud_upload_submit_idempotency_and_state(self):
        raw=(Path(__file__).parent/'fixtures/monthly_revenue.csv').read_bytes()
        d=self.service.upload(self.owner,{'name':'sales.csv','content_base64':base64.b64encode(raw).decode()})
        self.assertEqual(d['profile']['preparation'],'automatic-v2')
        plan=local_plan(d,{'question':'Show monthly revenue'})
        from types import SimpleNamespace
        agent=Mock(return_value=SimpleNamespace(structured_output=plan))
        with patch('analysis_engine.cloud_service.TrackedAgent',return_value=agent):
            r=self.service.submit(self.owner,{'dataset_id':d['id'],'question':'Show monthly revenue','request_key':'test'})
            self.service.pool.shutdown(wait=True)
        result=self.service.store.run(self.owner,r['id'])
        self.assertEqual(result['status'],'succeeded',result)
        self.assertEqual(result['result']['total'],579060)
        self.assertEqual(result['events'][-1]['status'],'completed')
        self.assertEqual([e['sequence'] for e in result['events']],list(range(1,len(result['events'])+1)))
        self.assertTrue(result['bundle_key'].endswith('/analysis.zip'))
        self.assertTrue(result['result']['visuals'])
        self.assertEqual(len(d['experience']['suggestions']),2)
        with self.assertRaises(InputError):
            self.service.dispatch({'owner':'b'*64,'action':'artifacts','payload':{'run_id':r['id']}})
        self.assertEqual(self.service.submit(self.owner,{'dataset_id':d['id'],'question':'Show monthly revenue','request_key':'test'})['id'],r['id'])
        with self.assertRaises(InputError):self.service.submit(self.owner,{'dataset_id':d['id'],'question':'Different','request_key':'test'})
        self.assertEqual(self.service.store.workspace('b'*64)['datasets'],[])
        compact=self.service.store.workspace(self.owner,compact=True)['runs'][0]
        self.assertNotIn('evidence',compact['result'])
        self.assertIn('evidence',self.service.store.run(self.owner,r['id'])['result'])
        with patch.object(self.service.store.s3,'generate_presigned_url',return_value='https://example.test/authorized') as sign:
            data=self.service.dispatch({'owner':self.owner,'action':'prepared_data','payload':{'run_id':r['id']}})
            self.assertEqual(data['expires_in'],120)
            self.assertEqual(sign.call_args.kwargs['Params']['Key'],self.owner+'/'+d['id']+'/dataset.parquet')
        with self.assertRaises(InputError):
            self.service.dispatch({'owner':'b'*64,'action':'prepared_data','payload':{'run_id':r['id']}})
        first=self.service.dispatch({'owner':self.owner,'action':'stream_ticket','payload':{'run_id':r['id']}})
        self.assertEqual(first['expires_in'],60)
        with self.assertRaises(InputError):self.service.dispatch({'owner':self.owner,'action':'stream_ticket','payload':{'run_id':r['id']}})
    def test_cancelled_job_does_not_invoke_a_model_or_publish(self):
        raw=(Path(__file__).parent/'fixtures/monthly_revenue.csv').read_bytes()
        d=self.service.upload(self.owner,{'name':'sales.csv','content_base64':base64.b64encode(raw).decode()})
        self.service.store.put(self.owner,'run','cancelled',{'id':'cancelled','dataset_id':d['id'],'status':'cancelled','created_at':0,'version_counter':0})
        with patch('analysis_engine.cloud_service.TrackedAgent') as agent:
            self.service.work(self.owner,'cancelled',d,None,None)
            agent.assert_not_called()

    def test_unknown_sandbox_outcome_retains_the_reservation(self):
        from types import SimpleNamespace
        raw=(Path(__file__).parent/'fixtures/monthly_revenue.csv').read_bytes()
        d=self.service.upload(self.owner,{'name':'sales.csv','content_base64':base64.b64encode(raw).decode()})
        plan=local_plan(d,{'question':'Forecast next three months'})
        agent=Mock(return_value=SimpleNamespace(structured_output=plan))
        with patch('analysis_engine.cloud_service.TrackedAgent',return_value=agent),patch('analysis_engine.cloud_service.run_forecast',side_effect=InputError('Unknown outcome.','outcome_unknown')):
            r=self.service.submit(self.owner,{'dataset_id':d['id'],'question':'Forecast next three months','request_key':'unknown'})
            self.service.pool.shutdown(wait=True)
        run=self.service.store.run(self.owner,r['id'])
        self.assertEqual(run['status'],'failed')
        self.assertEqual(self.service.quotas.status({'owner':self.owner,'kind':'member'})['remaining'],19)

    def test_unconfirmed_cleanup_retains_reservation_even_after_cancel_error(self):
        from types import SimpleNamespace
        raw=(Path(__file__).parent/'fixtures/monthly_revenue.csv').read_bytes()
        d=self.service.upload(self.owner,{'name':'sales.csv','content_base64':base64.b64encode(raw).decode()})
        plan=local_plan(d,{'question':'Forecast next three months'})
        agent=Mock(return_value=SimpleNamespace(structured_output=plan))
        with patch('analysis_engine.cloud_service.TrackedAgent',return_value=agent),patch('analysis_engine.cloud_service.CodeInterpreter',return_value=SimpleNamespace(cleanup_error='Stop not confirmed.')),patch('analysis_engine.cloud_service.run_forecast',side_effect=InputError('Cancelled.','cancelled')):
            self.service.submit(self.owner,{'dataset_id':d['id'],'question':'Forecast next three months','request_key':'cleanup'})
            self.service.pool.shutdown(wait=True)
        self.assertEqual(self.service.quotas.status({'owner':self.owner,'kind':'member'})['remaining'],19)

    def test_staged_upload_is_owner_scoped_bounded_and_removed(self):
        raw=(Path(__file__).parent/'fixtures/monthly_revenue.csv').read_bytes()
        upload_id='1'*32
        self.service.store.put_blob(self.owner,'incoming/'+upload_id,raw)
        with self.assertRaises(InputError):self.service.prepare_upload('b'*64,{'upload_id':upload_id,'name':'sales.csv'})
        dataset=self.service.prepare_upload(self.owner,{'upload_id':upload_id,'name':'sales.csv'})
        self.assertEqual(dataset['profile']['rows'],72)
        self.assertEqual(self.service.prepare_upload(self.owner,{'upload_id':upload_id,'name':'sales.csv'})['id'],dataset['id'])
        with self.assertRaises(InputError):self.service.prepare_upload(self.owner,{'upload_id':'../other','name':'sales.csv'})
        upload_id='2'*32
        self.service.store.put_blob(self.owner,'incoming/'+upload_id,b'x'*(10*1024*1024+1))
        with self.assertRaises(InputError) as err:self.service.prepare_upload(self.owner,{'upload_id':upload_id,'name':'sales.csv'})
        self.assertEqual(err.exception.code,'upload_limit')
        self.assertEqual(self.service.store.s3.list_objects_v2(Bucket=self.service.store.bucket,Prefix=self.owner+'/incoming/')['KeyCount'],0)


if __name__=='__main__':unittest.main()
