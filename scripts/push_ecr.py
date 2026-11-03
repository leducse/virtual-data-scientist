"""Push a locally built OCI archive using IAM APIs, without storing registry tokens."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import tarfile
from pathlib import Path
import boto3
from botocore.config import Config


def read_blob(archive,digest):
    if not re.fullmatch(r'sha256:[a-f0-9]{64}',digest):raise ValueError('Unexpected OCI digest')
    return archive.extractfile('blobs/sha256/'+digest.split(':')[1])


def push(client,archive_path,repository,tag):
    with tarfile.open(archive_path,'r') as archive:
        index=json.load(archive.extractfile('index.json'))
        descriptors=index['manifests']
        descriptor=next((d for d in descriptors if d.get('platform',{}).get('architecture')=='arm64'),descriptors[0])
        manifest_bytes=read_blob(archive,descriptor['digest']).read()
        manifest=json.loads(manifest_bytes)
        if 'manifests' in manifest:
            descriptor=next(d for d in manifest['manifests'] if d.get('platform',{}).get('architecture')=='arm64')
            manifest_bytes=read_blob(archive,descriptor['digest']).read();manifest=json.loads(manifest_bytes)
        config=json.load(read_blob(archive,manifest['config']['digest']))
        assert config['architecture']=='arm64' and config['os']=='linux'
        for blob in [manifest['config'],*manifest['layers']]:
            digest=blob['digest']
            response=client.batch_check_layer_availability(repositoryName=repository,layerDigests=[digest])
            if any(layer['layerAvailability']=='AVAILABLE' for layer in response.get('layers',[])):continue
            upload=client.initiate_layer_upload(repositoryName=repository)
            offset=0;hasher=hashlib.sha256()
            with read_blob(archive,digest) as stream:
                while part:=stream.read(10*1024*1024):
                    hasher.update(part)
                    client.upload_layer_part(repositoryName=repository,uploadId=upload['uploadId'],partFirstByte=offset,partLastByte=offset+len(part)-1,layerPartBlob=part)
                    offset+=len(part)
            if 'sha256:'+hasher.hexdigest()!=digest:raise ValueError('OCI layer checksum mismatch')
            client.complete_layer_upload(repositoryName=repository,uploadId=upload['uploadId'],layerDigests=[digest])
            print(f'Uploaded {digest[:24]} ({offset} bytes)',flush=True)
        response=client.put_image(repositoryName=repository,imageManifest=manifest_bytes.decode(),imageTag=tag,imageManifestMediaType=manifest['mediaType'])
        return response['image']['imageId']


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);p.add_argument('--repository',required=True);p.add_argument('--tag',required=True);p.add_argument('--region',default='us-east-1');p.add_argument('--execute',action='store_true')
    args=p.parse_args()
    if not args.execute:
        print('Review only: will upload OCI layers and manifest to the specified existing ECR repository. Use --execute for an authorized push.');return
    client=boto3.client('ecr',region_name=args.region,config=Config(connect_timeout=10,read_timeout=120,retries={'total_max_attempts':2}))
    print(json.dumps(push(client,args.archive,args.repository,args.tag)))


if __name__=='__main__':main()
