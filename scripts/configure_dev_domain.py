"""Prepare ACM DNS validation or publish the reviewed analytics subdomain alias."""
import argparse
import json
import time
from pathlib import Path

import boto3
from botocore.config import Config

DOMAIN='analyst.decision-layer.com'
ZONE='Z09581132N458QZSCIHJ4'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish-alias',action='store_true')
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if not args.execute:
        print('Review only: ACM certificate + DNS validation for '+DOMAIN+'; --publish-alias separately points the reviewed existing distribution.');return
    session=boto3.Session(region_name='us-east-1')
    cfg=Config(connect_timeout=5,read_timeout=20,retries={'total_max_attempts':2})
    assert session.client('sts',config=cfg).get_caller_identity()['Account']=='441383083571'
    dns=session.client('route53',config=cfg)
    target=Path(__file__).resolve().parents[1]/'docs/deployment/dev-domain.json'
    if args.publish_alias:
        distribution=session.client('cloudfront',config=cfg).get_distribution(Id='E3K5TU1GM2AOW4')['Distribution']
        assert DOMAIN in distribution['DistributionConfig']['Aliases']['Items'] and distribution['Status']=='Deployed'
        name=distribution['DomainName']
        existing=dns.list_resource_record_sets(HostedZoneId=ZONE,StartRecordName=DOMAIN,MaxItems='5')['ResourceRecordSets']
        for record in existing:
            if record['Name']==DOMAIN+'.' and record['Type'] in ('A','AAAA','CNAME'):
                assert record.get('AliasTarget',{}).get('DNSName','').rstrip('.')==name,'Subdomain already points elsewhere.'
        changes=[{'Action':'UPSERT','ResourceRecordSet':{'Name':DOMAIN,'Type':kind,
            'AliasTarget':{'HostedZoneId':'Z2FDTNDATAQYW2','DNSName':name,'EvaluateTargetHealth':False}}} for kind in ('A','AAAA')]
        result=dns.change_resource_record_sets(HostedZoneId=ZONE,ChangeBatch={'Comment':'Analytics development subdomain','Changes':changes})
        print(json.dumps({'domain':DOMAIN,'dns_change_id':result['ChangeInfo']['Id'],'distribution':name}),flush=True)
        return
    acm=session.client('acm',config=cfg)
    matches=[c for page in acm.get_paginator('list_certificates').paginate() for c in page['CertificateSummaryList'] if c['DomainName']==DOMAIN and c['Status'] in ('PENDING_VALIDATION','ISSUED')]
    arn=matches[0]['CertificateArn'] if matches else acm.request_certificate(DomainName=DOMAIN,ValidationMethod='DNS',IdempotencyToken='vds20261031',Tags=[{'Key':'Project','Value':'VirtualDataScientistV2Dev'}])['CertificateArn']
    for _ in range(60):
        cert=acm.describe_certificate(CertificateArn=arn)['Certificate']
        records=[r['ResourceRecord'] for r in cert.get('DomainValidationOptions',[]) if 'ResourceRecord' in r]
        if records:break
        time.sleep(2)
    else:raise RuntimeError('ACM did not produce a DNS validation record.')
    for record in records:
        dns.change_resource_record_sets(HostedZoneId=ZONE,ChangeBatch={'Comment':'Validate analytics TLS certificate','Changes':[{'Action':'UPSERT','ResourceRecordSet':{'Name':record['Name'],'Type':record['Type'],'TTL':300,'ResourceRecords':[{'Value':record['Value']}]}}]})
    acm.get_waiter('certificate_validated').wait(CertificateArn=arn,WaiterConfig={'Delay':5,'MaxAttempts':120})
    target.write_text(json.dumps({'domain':DOMAIN,'certificate_arn':arn,'status':'ISSUED','alias_published':False},indent=2)+'\n')
    print('Certificate issued; recorded '+str(target),flush=True)


if __name__=='__main__':main()
