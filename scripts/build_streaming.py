"""Package the pinned native Node Lambda streaming endpoint."""
import argparse
import subprocess
import zipfile
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('/tmp/vds-streaming.zip'))
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]/'aws_backend/streaming'
    subprocess.run(['npm','ci','--ignore-scripts','--omit=dev','--no-fund'],cwd=root,check=True)
    with zipfile.ZipFile(args.output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ['index.mjs','stream.mjs','speech.mjs','package.json','package-lock.json']:
            archive.write(root/name,name)
        for source in sorted((root/'node_modules').rglob('*')):
            if source.is_file():archive.write(source,source.relative_to(root))
    print(f'Built {args.output}: {args.output.stat().st_size} bytes')


if __name__=='__main__':main()
