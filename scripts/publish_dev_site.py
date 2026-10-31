"""Publish only approved static workspace assets to the separate dev site."""
import argparse
import json
from pathlib import Path

import boto3
from botocore.config import Config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    assets = {'index.html': ('static/index.html', 'text/html; charset=utf-8')}
    for name, kind in [('workspace.js', 'application/javascript'), ('experience.js', 'application/javascript'),
                       ('speech.js','application/javascript'),('pcm-worklet.js','application/javascript'),
                       ('vendor/plotly-basic-2.32.0.min.js','application/javascript'), ('auth.js', 'application/javascript'),
                       ('workspace.css', 'text/css'), ('favicon.svg', 'image/svg+xml'), ('monthly_revenue.csv', 'text/csv')]:
        assets['static/' + name] = ('static/' + name, kind)
    if not args.execute:
        print('Review only: publish ' + ', '.join(assets) + ', and public sign-in config to the new development site. Existing website unchanged.')
        return
    if args.manifest:outputs=json.loads(args.manifest.read_text())['outputs']
    else:
        stack=boto3.client('cloudformation',region_name='us-east-1').describe_stacks(StackName='VirtualDataScientistV2DevWeb')['Stacks'][0]
        outputs={o['OutputKey']:o['OutputValue'] for o in stack['Outputs']}
    client = boto3.client('s3', region_name='us-east-1', config=Config(connect_timeout=5, read_timeout=30, retries={'total_max_attempts': 2}))
    root = Path(__file__).resolve().parents[1]
    index=assets.pop('index.html');assets['index.html']=index
    for key, (source, kind) in assets.items():
        client.put_object(Bucket=outputs['SiteBucket'], Key=key, Body=(root / source).read_bytes(),
                          ContentType=kind, CacheControl='public,max-age=60', ServerSideEncryption='AES256')
    config = {'client_id': outputs['ClientId'], 'domain': outputs['LoginDomain'],'guest_enabled':outputs.get('GuestEnabled')=='true'}
    assert set(config) == {'client_id', 'domain','guest_enabled'}
    client.put_object(Bucket=outputs['SiteBucket'], Key='config.json', Body=json.dumps(config).encode(),
                      ContentType='application/json', CacheControl='no-store', ServerSideEncryption='AES256')
    boto3.client('cloudfront',region_name='us-east-1').create_invalidation(DistributionId=outputs['DistributionId'],
        InvalidationBatch={'CallerReference':__import__('uuid').uuid4().hex,'Paths':{'Quantity':4,'Items':['/','/index.html','/config.json','/static/*']}})
    print('Published development workspace: ' + outputs['WebUrl'])


if __name__ == '__main__': main()
