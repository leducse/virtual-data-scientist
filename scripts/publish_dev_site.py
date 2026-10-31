"""Publish only approved static workspace assets to the separate dev site."""
import argparse
import json
from pathlib import Path

import boto3
from botocore.config import Config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('docs/deployment/2026-10-31-hosted-web.json'))
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    assets = {'index.html': ('static/index.html', 'text/html; charset=utf-8')}
    for name, kind in [('workspace.js', 'application/javascript'), ('experience.js', 'application/javascript'),
                       ('vendor/plotly-basic-2.32.0.min.js','application/javascript'), ('auth.js', 'application/javascript'),
                       ('workspace.css', 'text/css'), ('favicon.svg', 'image/svg+xml'), ('monthly_revenue.csv', 'text/csv')]:
        assets['static/' + name] = ('static/' + name, kind)
    if not args.execute:
        print('Review only: publish ' + ', '.join(assets) + ', and public sign-in config to the new development site. Existing website unchanged.')
        return
    outputs = json.loads(args.manifest.read_text())['outputs']
    client = boto3.client('s3', region_name='us-east-1', config=Config(connect_timeout=5, read_timeout=30, retries={'total_max_attempts': 2}))
    root = Path(__file__).resolve().parents[1]
    for key, (source, kind) in assets.items():
        client.put_object(Bucket=outputs['SiteBucket'], Key=key, Body=(root / source).read_bytes(),
                          ContentType=kind, CacheControl='public,max-age=60', ServerSideEncryption='AES256')
    config = {'client_id': outputs['ClientId'], 'domain': outputs['LoginDomain']}
    assert set(config) == {'client_id', 'domain'}
    client.put_object(Bucket=outputs['SiteBucket'], Key='config.json', Body=json.dumps(config).encode(),
                      ContentType='application/json', CacheControl='no-store', ServerSideEncryption='AES256')
    print('Published development workspace: ' + outputs['WebUrl'])


if __name__ == '__main__': main()
