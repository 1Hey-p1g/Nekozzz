"""Preserve original notices from verified-version archives, without extraction of code."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    records = []
    sources = ROOT / 'report/clearance_sources'
    for archive in sorted(sources.glob('*.tar.*')):
        with tarfile.open(archive) as tree:
            referenced = set()
            for member in tree.getmembers():
                if member.isfile() and member.name.endswith('qt_attribution.json'):
                    try:
                        values = json.loads(tree.extractfile(member).read())
                    except json.JSONDecodeError:
                        continue
                    for value in values if isinstance(values, list) else [values]:
                        names = value.get('LicenseFile', [])
                        for name in names if isinstance(names, list) else [names]:
                            referenced.add(str(PurePosixPath(member.name).parent / name))
            for item in tree.getmembers():
                path = PurePosixPath(item.name)
                if not item.isfile() or '..' in path.parts or path.is_absolute():
                    continue
                filename = path.name.lower()
                notice = (filename.startswith(('license', 'licence', 'copying', 'copyright', 'notice'))
                          or filename in ('qt_attribution.json', 'reuse.toml')
                          or item.name in referenced)
                if not notice or item.size > 500000:
                    continue
                data = tree.extractfile(item).read()
                target = ROOT / 'licenses/upstream_sources' / Path(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                records.append(dict(archive=archive.name, member=item.name,
                                    notice=target.relative_to(ROOT).as_posix(),
                                    sha256=hashlib.sha256(data).hexdigest(),
                                    scope='source evidence; inclusion in binary not implied'))
    (ROOT / 'report/clearance/extracted_notices.json').write_text(
        json.dumps(records, indent=2), encoding='utf-8')
    print('Preserved', len(records), 'original upstream notices')


if __name__ == '__main__':
    main()
