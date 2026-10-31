"""Deploy reviewed artifacts only to the existing, explicitly authorized development stacks."""
import argparse
import hashlib
import json
import time
from pathlib import Path

import boto3
from botocore.config import Config


def update(client, name, template_path, changes):
    stack=client.describe_stacks(StackName=name)['Stacks'][0]
    known={p['ParameterKey'] for p in stack['Parameters']}
    template=json.loads(template_path.read_text())
    parameters=[{'ParameterKey':key,'ParameterValue':str(changes[key])} if key in changes else {'ParameterKey':key,'UsePreviousValue':True}
                for key in template.get('Parameters',{}) if key in known or key in changes]
    change_name='vds-'+str(int(time.time()))
    client.create_change_set(StackName=name,ChangeSetName=change_name,ChangeSetType='UPDATE',
        TemplateBody=json.dumps(template),Parameters=parameters,Capabilities=['CAPABILITY_NAMED_IAM'])
    client.get_waiter('change_set_create_complete').wait(StackName=name,ChangeSetName=change_name,WaiterConfig={'Delay':2,'MaxAttempts':60})
    change=client.describe_change_set(StackName=name,ChangeSetName=change_name)
    if any(c['ResourceChange'].get('Replacement')=='True' or c['ResourceChange']['Action']=='Remove' for c in change.get('Changes',[])):
        raise RuntimeError('Development update would replace or remove a resource; inspect the saved change set before proceeding.')
    print(json.dumps({'stack':name,'changes':[c['ResourceChange'] for c in change.get('Changes',[])]}),flush=True)
    client.execute_change_set(StackName=name,ChangeSetName=change_name)
    client.get_waiter('stack_update_complete').wait(StackName=name,WaiterConfig={'Delay':5,'MaxAttempts':180})
    return client.describe_stacks(StackName=name)['Stacks'][0]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release',required=True)
    parser.add_argument('--image-digest')
    parser.add_argument('--gateway-zip',type=Path)
    parser.add_argument('--stream-zip',type=Path)
    parser.add_argument('--domain')
    parser.add_argument('--certificate')
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if not args.execute:
        print('Review only: existing VirtualDataScientistV2Dev and VirtualDataScientistV2DevWeb in us-east-1. No public launch or unrelated stacks.');return
    root=Path(__file__).resolve().parents[1]
    session=boto3.Session(region_name='us-east-1')
    cfg=Config(connect_timeout=5,read_timeout=30,retries={'total_max_attempts':2})
    assert session.client('sts',config=cfg).get_caller_identity()['Account']=='441383083571'
    cf=session.client('cloudformation',config=cfg)
    output={'release':args.release}
    if args.image_digest or args.domain:
        changes={}
        if args.image_digest:
            assert args.image_digest.startswith('sha256:') and len(args.image_digest)==71
            changes.update(ImageUri='441383083571.dkr.ecr.us-east-1.amazonaws.com/virtual-data-scientist-v2-dev@'+args.image_digest,ReleaseId=args.release)
        if args.domain:changes.update(WebOrigin='https://'+args.domain,AlternateOrigin='https://d19bkp3wlr8r7k.cloudfront.net')
        stack=update(cf,'VirtualDataScientistV2Dev',root/'aws_backend/cloud-dev/template.json',changes)
        output['runtime_status']=stack['StackStatus']
    if args.gateway_zip or args.stream_zip or args.domain:
        core=cf.describe_stacks(StackName='VirtualDataScientistV2Dev')['Stacks'][0]
        core_outputs={o['OutputKey']:o['OutputValue'] for o in core['Outputs']}
        bucket=core_outputs['DataBucket']
        s3=session.client('s3',config=cfg)
        changes={}
        for source,param in [(args.gateway_zip,'CodeKey'),(args.stream_zip,'StreamCodeKey')]:
            if source:
                data=source.read_bytes();digest=hashlib.sha256(data).hexdigest();key='deployment/'+digest+'.zip'
                s3.put_object(Bucket=bucket,Key=key,Body=data,ContentType='application/zip',ServerSideEncryption='AES256')
                changes[param]=key
                output[param+'_sha256']=digest
        changes['StateTable']=core_outputs['StateTable']
        if args.domain:
            assert args.domain=='analyst.decision-layer.com' and args.certificate
            changes.update(CustomDomain=args.domain,CertificateArn=args.certificate,AppOrigin='https://'+args.domain)
        changes={k:v for k,v in changes.items() if k in json.loads((root/'aws_backend/cloud-dev/web-template.json').read_text())['Parameters']}
        stack=update(cf,'VirtualDataScientistV2DevWeb',root/'aws_backend/cloud-dev/web-template.json',changes)
        output['web_status']=stack['StackStatus']
        output['outputs']={o['OutputKey']:o['OutputValue'] for o in stack['Outputs']}
    target=root/'docs/deployment'/f'{args.release}.json'
    target.write_text(json.dumps(output,indent=2)+'\n')
    print('Recorded '+str(target),flush=True)


if __name__=='__main__':main()
