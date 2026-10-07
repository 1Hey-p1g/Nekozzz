"""Report potential publication data without printing sensitive values or modifying it."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def main():
    patterns = {
        'credential_assignment': re.compile(r'(?i)(?:password|passwd|secret|api_key|access_key|token)\s*[:=]\s*[\"\'][^\"\']+[\"\']'),
        'private_key_header': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
        'identity_number_candidate': re.compile(r'(?<!\d)\d{17}[\dXx](?!\d)'),
        'phone_candidate': re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)'),
        'absolute_user_path': re.compile(r'(?i)[A-Z]:[\\/]Users[\\/][^\s\"\'<>]+'),
    }
    hits = []
    for folder in ('gui', 'services', 'repositories', 'database', 'migration', 'config', 'tools', 'tests'):
        for path in (ROOT / folder).rglob('*.py'):
            if '__pycache__' in path.parts:
                continue
            for number, line in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
                for category, pattern in patterns.items():
                    if pattern.search(line):
                        hits.append(dict(path=path.relative_to(ROOT).as_posix(), line=number, category=category,
                                         value_sha256=hashlib.sha256(line.encode()).hexdigest(),
                                         status='candidate; requires context/manual review, value not reproduced'))
    bundle = ROOT / 'dist/Nekozzz'
    disallowed = [p.relative_to(bundle).as_posix() for p in bundle.rglob('*')
                  if p.is_file() and (p.suffix.lower() in ('.db', '.sqlite', '.accdb', '.mdb')
                                     or p.name == 'settings.json')]
    result = dict(scope='allowlisted application/test Python sources; actual formal bundle data-file inventory',
                  candidate_hits=hits, bundle_user_data_files=disallowed,
                  limits='Does not establish real-name provenance or inspect real Images/Access business contents; not a no-PII guarantee',
                  office_metadata_evidence='report/NEKOZZZ_RESOURCE_METADATA_AUDIT.json (same protected file hashes)',
                  exclude_from_publication=['database data', 'Access data', 'Images', 'Backups', 'settings.json',
                                            'build', 'dist/prune_experiments', '.venv', 'raw generated logs', 'generated DOCX'])
    (ROOT / 'report/clearance/privacy_scan.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(len(hits), 'source candidates;', len(disallowed), 'formal bundle user-data files')


if __name__ == '__main__':
    main()
