import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from botocore.exceptions import WaiterError
from scripts.deploy_dev import update
from scripts.configure_dev_domain import main as configure_domain


class DeploymentRetryTests(unittest.TestCase):
    def change(self,reason):
        client=Mock()
        stack={'Parameters':[],'StackStatus':'UPDATE_COMPLETE'}
        client.describe_stacks.return_value={'Stacks':[stack]}
        client.get_waiter.return_value.wait.side_effect=WaiterError(name='change_set_create_complete',reason='failed',last_response={})
        client.describe_change_set.return_value={'Status':'FAILED','StatusReason':reason}
        return client,stack

    def test_unchanged_stack_allows_deployment_retry_to_continue(self):
        client,stack=self.change("The submitted information didn't contain changes. Submit different information to create a change set.")
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'template.json';path.write_text(json.dumps({'Parameters':{}}))
            self.assertEqual(update(client,'development',path,{}),stack)
        client.execute_change_set.assert_not_called()

    def test_other_change_set_failures_are_not_swallowed(self):
        client,_=self.change('Access denied to a required resource')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'template.json';path.write_text('{}')
            with self.assertRaises(WaiterError):update(client,'development',path,{})

    def test_dns_publication_refuses_incomplete_tls_propagation_and_unrelated_target(self):
        domain='mlworkbench.decision-layer.com';previous='analyst.decision-layer.com'
        for failure in ('propagation','certificate','unrelated_record'):
            with self.subTest(failure=failure):
                clients={name:Mock() for name in ('sts','route53','cloudfront','acm')}
                clients['sts'].get_caller_identity.return_value={'Account':'441383083571'}
                clients['route53'].get_hosted_zone.return_value={'HostedZone':{'Name':'decision-layer.com.'}}
                clients['cloudfront'].get_distribution.return_value={'Distribution':{
                    'Status':'InProgress' if failure=='propagation' else 'Deployed','DomainName':'d19bkp3wlr8r7k.cloudfront.net',
                    'DistributionConfig':{'Aliases':{'Items':[domain,previous]},'ViewerCertificate':{'ACMCertificateArn':'certificate'}}}}
                clients['acm'].describe_certificate.return_value={'Certificate':{'Status':'ISSUED',
                    'SubjectAlternativeNames':[previous] if failure=='certificate' else [domain,previous]}}
                clients['route53'].list_resource_record_sets.return_value={'ResourceRecordSets':[
                    {'Name':domain+'.','Type':'CNAME','ResourceRecords':[{'Value':'somewhere-else.example.com'}]}]}
                with patch('sys.argv',['configure_dev_domain.py','--publish-alias','--execute']),patch('scripts.configure_dev_domain.boto3.Session') as session:
                    session.return_value.client.side_effect=lambda name,**kwargs:clients[name]
                    with self.assertRaises(AssertionError):configure_domain()
                clients['route53'].change_resource_record_sets.assert_not_called()
