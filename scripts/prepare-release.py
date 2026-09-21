#!/usr/bin/env python3
"""Build a local source archive without publishing or modifying Git."""
import argparse
import json
from pathlib import Path
import tarfile
from release_files import public_files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='New archive path; refuses overwrite')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    version = json.loads((root / 'manifest.json').read_text())['version']
    name = 'omatask-' + version
    output = args.output or root / '.local/release' / (name + '.tar.gz')
    files = list(public_files(root, include_tests=True))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream, tarfile.open(fileobj=stream, mode='w:gz') as archive:
        for relative in files:
            info = archive.gettarinfo(str(root / relative), arcname=str(Path(name) / relative))
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            info.mtime = 0
            with (root / relative).open('rb') as source:
                archive.addfile(info, source)
    print(output)


if __name__ == '__main__':
    main()
