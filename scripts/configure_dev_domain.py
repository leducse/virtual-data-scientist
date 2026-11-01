"""Validate TLS, then publish the authorized development subdomain on the existing distribution."""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path

import boto3
from botocore.config import Config

ZONE='Z09581132N458QZSCIHJ4'
DISTRIBUTION='E3K5TU1GM2AOW4'


def valid_domain(value):
    return bool(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.decision-layer\.com',value))


def existing_records(dns,name):
    return [r for r in dns.list_resource_record_sets(HostedZoneId=ZONE,StartRecordName=name,MaxItems='5')['ResourceRecordSets']
            if r['Name'].rstrip('.')==name.rstrip('.')]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain',default='mlworkbench.decision-layer.com')
    parser.add_argument('--previous-domain',default='analyst.decision-layer.com')
    parser.add_argument('--publish-alias',action='store_true')
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if not valid_domain(args.domain) or (args.previous_domain and (not valid_domain(args.previous_domain) or args.previous_domain==args.domain)):
        parser.error('Use distinct subdomains within decision-layer.com.')
    domains=sorted({args.domain,args.previous_domain}-{''})
    if not args.execute:
        print(json.dumps({'review_only':True,'domains':domains,'distribution':DISTRIBUTION,'publish_alias':args.publish_alias}));return
    session=boto3.Session(region_name='us-east-1')
    cfg=Config(connect_timeout=5,read_timeout=20,retries={'total_max_attempts':2})
    assert session.client('sts',config=cfg).get_caller_identity()['Account']=='441383083571'
    dns=session.client('route53',config=cfg)
    assert dns.get_hosted_zone(Id=ZONE)['HostedZone']['Name']=='decision-layer.com.'
    target=Path(__file__).resolve().parents[1]/'docs/deployment'/('dev-domain-'+args.domain.split('.')[0]+'.json')
    acm=session.client('acm',config=cfg)
    if args.publish_alias:
        distribution=session.client('cloudfront',config=cfg).get_distribution(Id=DISTRIBUTION)['Distribution']
        config=distribution['DistributionConfig']
        assert set(domains).issubset(config['Aliases'].get('Items',[])) and distribution['Status']=='Deployed'
        cert=acm.describe_certificate(CertificateArn=config['ViewerCertificate']['ACMCertificateArn'])['Certificate']
        assert cert['Status']=='ISSUED' and set(domains).issubset(cert['SubjectAlternativeNames'])
        name=distribution['DomainName']
        for record in existing_records(dns,args.domain):
            if record['Type'] in ('A','AAAA','CNAME'):
                assert record.get('AliasTarget',{}).get('DNSName','').rstrip('.')==name,'Subdomain already points elsewhere.'
        changes=[{'Action':'UPSERT','ResourceRecordSet':{'Name':args.domain,'Type':kind,
            'AliasTarget':{'HostedZoneId':'Z2FDTNDATAQYW2','DNSName':name,'EvaluateTargetHealth':False}}} for kind in ('A','AAAA')]
        result=dns.change_resource_record_sets(HostedZoneId=ZONE,ChangeBatch={'Comment':'ML Workbench development subdomain','Changes':changes})
        dns.get_waiter('resource_record_sets_changed').wait(Id=result['ChangeInfo']['Id'],WaiterConfig={'Delay':5,'MaxAttempts':120})
        doc=json.loads(target.read_text())
        doc.update(alias_published=True,dns_change_id=result['ChangeInfo']['Id'],distribution=name)
        target.write_text(json.dumps(doc,indent=2)+'\n')
        print(json.dumps(doc),flush=True);return
    arn=None
    for page in acm.get_paginator('list_certificates').paginate():
        for item in page['CertificateSummaryList']:
            if item['DomainName']==args.domain and item['Status'] in ('PENDING_VALIDATION','ISSUED'):
                cert=acm.describe_certificate(CertificateArn=item['CertificateArn'])['Certificate']
                if set(domains).issubset(cert['SubjectAlternativeNames']):arn=item['CertificateArn'];break
        if arn:break
    if not arn:
        arn=acm.request_certificate(DomainName=args.domain,SubjectAlternativeNames=domains,ValidationMethod='DNS',
            IdempotencyToken=hashlib.sha256(','.join(domains).encode()).hexdigest()[:32],
            Tags=[{'Key':'Project','Value':'VirtualDataScientistV2Dev'}])['CertificateArn']
    for _ in range(60):
        cert=acm.describe_certificate(CertificateArn=arn)['Certificate']
        validation=cert.get('DomainValidationOptions',[])
        if set(domains).issubset({v['DomainName'] for v in validation if 'ResourceRecord' in v}):break
        time.sleep(2)
    else:raise RuntimeError('ACM did not produce all DNS validation records.')
    for option in validation:
        record=option['ResourceRecord']
        for old in existing_records(dns,record['Name']):
            assert old['Type']==record['Type'] and old.get('ResourceRecords')==[{'Value':record['Value']}],'Validation record already points elsewhere.'
        dns.change_resource_record_sets(HostedZoneId=ZONE,ChangeBatch={'Comment':'Validate ML Workbench TLS certificate','Changes':[
            {'Action':'UPSERT','ResourceRecordSet':{'Name':record['Name'],'Type':record['Type'],'TTL':300,'ResourceRecords':[{'Value':record['Value']}]}}]})
    acm.get_waiter('certificate_validated').wait(CertificateArn=arn,WaiterConfig={'Delay':5,'MaxAttempts':120})
    target.write_text(json.dumps({'domain':args.domain,'previous_domain':args.previous_domain,'certificate_arn':arn,'status':'ISSUED','alias_published':False},indent=2)+'\n')
    print('Certificate issued; recorded '+str(target),flush=True)


if __name__=='__main__':main()
