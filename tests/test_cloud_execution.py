import io
import json
import threading
import unittest
from botocore.session import get_session
from botocore.validate import validate_parameters
from analysis_engine.cloud_execution import CodeInterpreter, ExecutionFailure
from analysis_engine.ingestion import InputError


class FakeInterpreter:
    def __init__(self, failure=None):
        self.calls=[];self.failure=failure
        self.model=get_session().get_service_model('bedrock-agentcore')
    def start_code_interpreter_session(self,**kwargs):
        validate_parameters(kwargs,self.model.operation_model('StartCodeInterpreterSession').input_shape)
        self.calls.append(('start',kwargs));return {'sessionId':'session-1'}
    def invoke_code_interpreter(self,**kwargs):
        validate_parameters(kwargs,self.model.operation_model('InvokeCodeInterpreter').input_shape)
        self.calls.append((kwargs['name'],kwargs))
        if self.failure and kwargs['name']=='executeCode':raise self.failure
        return {'stream':iter([{'result':{'isError':False,'structuredContent':{'stdout':'{"total":42}','exitCode':0}}}])}
    def stop_code_interpreter_session(self,**kwargs):
        validate_parameters(kwargs,self.model.operation_model('StopCodeInterpreterSession').input_shape)
        self.calls.append(('stop',kwargs));return {}


class CloudContractTests(unittest.TestCase):
    def test_blob_transfer_execute_and_cleanup_match_sdk_shapes(self):
        client=FakeInterpreter();runner=CodeInterpreter(client,'aws.codeinterpreter.v1')
        result=runner.execute(b'PAR1fake','print(42)')
        self.assertEqual([name for name,_ in client.calls],['start','writeFiles','executeCode','stop'])
        self.assertEqual(client.calls[1][1]['arguments']['content'],[{'path':'dataset.parquet','blob':b'PAR1fake'}])
        self.assertEqual(result['execution'],'agentcore_code_interpreter')
        self.assertIsNone(runner.cleanup_error)

    def test_unknown_outcome_not_retried_and_always_stopped(self):
        client=FakeInterpreter(TimeoutError('lost response'))
        with self.assertRaises(ExecutionFailure) as e:CodeInterpreter(client,'aws.codeinterpreter.v1').execute(b'fake','print(1)')
        self.assertEqual(e.exception.code,'outcome_unknown')
        self.assertEqual([n for n,_ in client.calls].count('executeCode'),1)
        self.assertEqual(client.calls[-1][0],'stop')

    def test_cancel_before_execution_stops_session(self):
        cancel=threading.Event();cancel.set();client=FakeInterpreter()
        with self.assertRaises(ExecutionFailure) as e:CodeInterpreter(client,'aws.codeinterpreter.v1').execute(b'fake','print(1)',cancel)
        self.assertEqual(e.exception.code,'cancelled')
        self.assertEqual([n for n,_ in client.calls],['start','stop'])

    def test_output_budget_and_service_error_cleanup(self):
        for event in [{'accessDeniedException':{'message':'denied'}},{'result':{'isError':True}}, {'result':{'content':[{'type':'text','text':'x'*(2*1024*1024)}]}}]:
            client=FakeInterpreter()
            original=client.invoke_code_interpreter
            def invoke(**kwargs):
                if kwargs['name']=='writeFiles':return original(**kwargs)
                return {'stream':iter([event])}
            client.invoke_code_interpreter=invoke
            with self.assertRaises(ExecutionFailure):CodeInterpreter(client,'aws.codeinterpreter.v1').execute(b'fake','print(1)')
            self.assertEqual(client.calls[-1][0],'stop')

    def test_file_retrieval_and_session_reuse_are_bounded(self):
        client=FakeInterpreter();runner=CodeInterpreter(client,'aws.codeinterpreter.v1')
        result=runner.execute(b'fake','print(1)',files={'plan.json':'{}'},output_files=['plot.png'])
        self.assertEqual([n for n,_ in client.calls],['start','writeFiles','executeCode','readFiles','stop'])
        self.assertTrue(result['artifacts'])
        with self.assertRaises(InputError):runner.execute(b'fake','print(2)')

    def test_cancellation_during_execution_stops_session(self):
        cancel=threading.Event();client=FakeInterpreter()
        original=client.invoke_code_interpreter
        stopped=threading.Event()
        original_stop=client.stop_code_interpreter_session
        def stop(**kwargs):
            original_stop(**kwargs);stopped.set()
        def invoke(**kwargs):
            if kwargs['name']=='executeCode':
                cancel.set()
                self.assertTrue(stopped.wait(2))
            return original(**kwargs)
        client.invoke_code_interpreter=invoke;client.stop_code_interpreter_session=stop
        with self.assertRaises(ExecutionFailure) as e:CodeInterpreter(client,'aws.codeinterpreter.v1').execute(b'fake','print(1)',cancel)
        self.assertEqual(e.exception.code,'cancelled')
        self.assertEqual([n for n,_ in client.calls].count('stop'),1)

    def test_deadline_stops_session_and_unfinished_task_is_unknown(self):
        client=FakeInterpreter();original=client.invoke_code_interpreter
        stopped=threading.Event();original_stop=client.stop_code_interpreter_session
        def stop(**kwargs):original_stop(**kwargs);stopped.set()
        def invoke(**kwargs):
            if kwargs['name']=='executeCode':self.assertTrue(stopped.wait(2))
            return original(**kwargs)
        client.invoke_code_interpreter=invoke;client.stop_code_interpreter_session=stop
        with self.assertRaises(ExecutionFailure) as e:CodeInterpreter(client,'aws.codeinterpreter.v1',1).execute(b'fake','print(1)')
        self.assertEqual(e.exception.code,'deadline_exceeded')
        client=FakeInterpreter();original=client.invoke_code_interpreter
        def unfinished(**kwargs):
            if kwargs['name']=='executeCode':return {'stream':iter([{'result':{'structuredContent':{'taskStatus':'working'}}}])}
            return original(**kwargs)
        client.invoke_code_interpreter=unfinished
        with self.assertRaises(ExecutionFailure) as e:CodeInterpreter(client,'aws.codeinterpreter.v1').execute(b'fake','print(1)')
        self.assertEqual(e.exception.code,'outcome_unknown')

    def test_builtin_metadata_omission_is_bound_to_the_system_arn(self):
        from scripts.cloud_smoke import validate_configuration
        validate_configuration({'codeInterpreterArn':'arn:aws:bedrock-agentcore:us-east-1:aws:code-interpreter/aws.codeinterpreter.v1'},'aws.codeinterpreter.v1','us-east-1')
        with self.assertRaises(RuntimeError):validate_configuration({},'aws.codeinterpreter.v1','us-east-1')
        with self.assertRaises(RuntimeError):validate_configuration({'networkConfiguration':{'networkMode':'PUBLIC'}},'custom','us-east-1')


if __name__=='__main__':unittest.main()
