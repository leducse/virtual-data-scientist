import io
import json
import tempfile
import time
import unittest
from pathlib import Path
import boto3
from moto import mock_aws
from analysis_engine.cloud_store import CloudStore
from analysis_engine.ingestion import InputError, parse_table


@mock_aws
class CloudStoreTests(unittest.TestCase):
    def setUp(self):
        self.s3=boto3.client('s3',region_name='us-east-1');self.s3.create_bucket(Bucket='vds-test-data')
        db=boto3.resource('dynamodb',region_name='us-east-1')
        table=db.create_table(TableName='vds-test-state',KeySchema=[{'AttributeName':'pk','KeyType':'HASH'},{'AttributeName':'sk','KeyType':'RANGE'}],AttributeDefinitions=[{'AttributeName':'pk','AttributeType':'S'},{'AttributeName':'sk','AttributeType':'S'}],BillingMode='PAY_PER_REQUEST')
        self.store=CloudStore(self.s3,table,'vds-test-data')
        self.alice='a'*64;self.bob='b'*64;self.dataset='d'*32;self.run='e'*32
        self.store.put(self.alice,'dataset',self.dataset,{'id':self.dataset,'created_at':time.time()},create=True)
        self.store.put(self.alice,'run',self.run,{'id':self.run,'dataset_id':self.dataset,'status':'queued','created_at':time.time(),'version_counter':0},create=True)

    def test_conditional_state_idempotency_owner_and_terminal_guard(self):
        with self.assertRaises(self.store.table.meta.client.exceptions.ConditionalCheckFailedException):
            self.store.put(self.alice,'dataset',self.dataset,{},create=True)
        with self.assertRaises(InputError):self.store.dataset(self.bob,self.dataset)
        self.assertTrue(self.store.update_run(self.alice,self.run,status='cancelled'))
        self.assertFalse(self.store.update_run(self.alice,self.run,status='succeeded'))
        self.assertEqual(self.store.run(self.alice,self.run)['status'],'cancelled')

    def test_global_and_owner_admission_and_release(self):
        one=self.store.acquire(self.alice,'run1')
        with self.assertRaises(InputError):self.store.acquire(self.alice,'run2')
        two=self.store.acquire(self.bob,'run3')
        with self.assertRaises(InputError):self.store.acquire('c'*64,'run4')
        self.store.release(one,'unrelated-run')
        with self.assertRaises(InputError):self.store.acquire(self.alice,'run5')
        self.store.release(one,'run1');self.store.release(two,'run3')
        self.assertTrue(self.store.acquire(self.alice,'run6'))

    def test_saved_result_reopens_and_delete_revokes_then_purges(self):
        key=f'{self.dataset}/runs/{self.run}.json'
        self.store.put_blob(self.alice,key,b'{"total":42}')
        self.store.update_run(self.alice,self.run,status='succeeded',result_key=key)
        reopened=CloudStore(self.s3,self.store.table,'vds-test-data')
        self.assertEqual(reopened.run(self.alice,self.run)['result']['total'],42)
        reopened.delete(self.alice,self.dataset)
        with self.assertRaises(InputError):self.store.run(self.alice,self.run)
        self.assertEqual(self.s3.list_objects_v2(Bucket='vds-test-data').get('KeyCount'),0)
        self.assertEqual(self.store.workspace(self.alice)['runs'],[])

    def test_expired_execution_is_interrupted_without_replay(self):
        self.store.put(self.alice,'run',self.run,{'id':self.run,'dataset_id':self.dataset,'status':'running','created_at':time.time()-500,'version_counter':0})
        self.assertEqual(self.store.run(self.alice,self.run)['status'],'interrupted')

    def test_compact_history_stays_bounded_and_full_evidence_is_retrievable(self):
        for index in range(3):
            run_id=str(index)*32
            key=f'{self.dataset}/runs/{run_id}.json'
            self.store.put_blob(self.alice,key,json.dumps({'series':['x'*1100000],'evidence':{'source':'trusted'}}).encode())
            self.store.put(self.alice,'run',run_id,{'id':run_id,'dataset_id':self.dataset,'status':'succeeded','created_at':time.time()+index,'result_key':key})
        compact=self.store.workspace(self.alice,compact=True)
        self.assertLess(len(json.dumps(compact).encode()),2200000)
        saved=[r for r in compact['runs'] if r.get('result_available')]
        self.assertEqual(len(saved),3)
        hidden=next(r for r in saved if not r.get('result'))
        self.assertEqual(self.store.run(self.alice,hidden['id'])['result']['evidence']['source'],'trusted')


class AutomaticPreparationTests(unittest.TestCase):
    def test_title_delimiter_currency_percentage_and_identifier(self):
        raw=b'Quarterly sales export\naccount_code;transaction_date;Net Sales;rate\n001;2024-01-15;$1,200.50;20%\n002;2024-02-15;$2,300.50;25%\n'
        table,profile=parse_table('sales.csv',raw)
        self.assertEqual(profile['header_row'],2)
        self.assertEqual(table['account_code'].to_pylist(),['001','002'])
        self.assertEqual(table['Net Sales'].to_pylist(),[1200.5,2300.5])
        self.assertEqual(table['rate'].to_pylist(),[.2,.25])
        self.assertEqual(profile['columns'][2]['units'],'USD')

    def test_multi_table_ambiguity_is_a_business_question(self):
        import openpyxl
        b=openpyxl.Workbook();b.active.title='Sales';b.create_sheet('Returns')
        for title in b.sheetnames:
            b[title].append(['date','amount']);b[title].append(['2024-01-15',10])
        output=io.BytesIO();b.save(output)
        with self.assertRaises(InputError) as e:parse_table('sales.xlsx',output.getvalue())
        self.assertEqual(e.exception.code,'clarification_required')
        self.assertIn('Which business dataset',str(e.exception))
        table,profile=parse_table('sales.xlsx',output.getvalue(),business_context='Analyze Sales')
        self.assertEqual(profile['sheet'],'Sales')
        self.assertEqual(table.num_rows,1)


if __name__=='__main__':unittest.main()
