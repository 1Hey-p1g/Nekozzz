"""Prepare a local, allowlisted application-source candidate; not publication."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = []
    for folder in ('gui', 'services', 'repositories', 'database', 'migration', 'config', 'tools', 'tests'):
        files += [p for p in (ROOT / folder).rglob('*.py') if '__pycache__' not in p.parts]
    for folder in ('resources', 'ui', 'licenses'):
        files += [p for p in (ROOT / folder).rglob('*') if p.is_file()]
    names = ('main.py', 'version.py', 'Nekozzz.spec', 'build_windows.ps1',
             'requirements.txt', 'requirements-build.txt', '.gitignore',
             'LICENSE', 'README.md', 'BUILD_WINDOWS.md', 'THIRD_PARTY_NOTICES.md',
             'SOURCE_AVAILABILITY.md', 'access source/DatabaseStructure.xlsx')
    files += [ROOT / name for name in names if (ROOT / name).is_file()]
    output = ROOT / 'report/clearance_sources/Nekozzz-0.9.2-source-candidate.zip'
    records = []
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(files)):
            relative = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            info = zipfile.ZipInfo('Nekozzz-0.9.2/' + relative, (2026, 10, 3, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
            records.append(dict(path=relative, sha256=hashlib.sha256(data).hexdigest()))
    manifest = dict(artifact=output.name, sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                    status='LOCAL CANDIDATE; Excel/document metadata and complete build-source correspondence require review',
                    excluded=['databases', 'Access data', 'Images', 'settings.json', 'backups', '.venv', 'build', 'dist', 'raw logs'],
                    files=records)
    (output.parent / 'Nekozzz-0.9.2-source-candidate.manifest.json').write_text(
        json.dumps(manifest, indent=2), encoding='utf-8')
    print(len(records), 'source/notice files; local candidate only')


if __name__ == '__main__':
    main()
