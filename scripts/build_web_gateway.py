"""Build the small ARM64 Lambda ZIP without bundling analytics or credentials."""
import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('/tmp/vds-web-gateway.zip'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='vds-web-package-') as folder:
        package = Path(folder)
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-compile', '--only-binary=:all:',
            '--platform', 'manylinux_2_28_aarch64', '--platform', 'manylinux2014_aarch64',
            '--implementation', 'cp', '--python-version', '3.13', '--target', folder,
            '-r', str(root / 'requirements-web.txt')], check=True)
        (package / 'web_gateway.py').write_bytes((root / 'aws_backend/web_gateway.py').read_bytes())
        (package / 'web_sessions.py').write_bytes((root / 'aws_backend/web_sessions.py').read_bytes())
        with zipfile.ZipFile(args.output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for source in sorted(package.rglob('*')):
                if source.is_file(): archive.write(source, source.relative_to(package))
        with zipfile.ZipFile(args.output) as archive:
            assert 'web_gateway.py' in archive.namelist()
            assert not any(name.startswith(('analysis_engine/', '.env', '.aws/')) for name in archive.namelist())
    print(f'Built {args.output}: {args.output.stat().st_size} bytes')


if __name__ == '__main__': main()
