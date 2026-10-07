"""Static source/binary evidence; does not change application files or user data."""
import hashlib
import json
from pathlib import Path
import re
import tarfile
import pefile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'report/clearance'


def main():
    OUT.mkdir(exist_ok=True)
    headers, attributions = [], []
    for archive in (ROOT / 'report/clearance_sources').glob('qt*.tar.xz'):
        with tarfile.open(archive) as tree:
            for item in tree.getmembers():
                if not item.isfile():
                    continue
                if item.name.endswith('qt_attribution.json'):
                    raw = tree.extractfile(item).read()
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError as error:
                        data = {'parse_error': str(error), 'original_sha256': hashlib.sha256(raw).hexdigest()}
                    attributions.append(dict(archive=archive.name, member=item.name, attribution=data,
                                             compiled_in_binary='not established solely by source attribution'))
                if item.name.endswith(('.cpp', '.h')) and '/3rdparty/' not in item.name:
                    head = tree.extractfile(item).read(1500).decode('utf-8', errors='replace')
                    match = re.search(r'SPDX-License-Identifier:\s*([^\r\n]+)', head)
                    if match:
                        headers.append(dict(archive=archive.name, member=item.name, license=match.group(1)))
    (OUT / 'qt_source_licenses.json').write_text(json.dumps(headers, indent=2), encoding='utf-8')
    (OUT / 'qt_source_attributions.json').write_text(json.dumps(attributions, indent=2), encoding='utf-8')
    paths = [ROOT / 'dist/Nekozzz/_internal/PySide6/opengl32sw.dll']
    paths += list(OUT.glob('opengl_*/opengl32sw.dll'))
    comparison = []
    for path in paths:
        data = path.read_bytes()
        pe = pefile.PE(data=data)
        sections = {s.Name.decode(errors='replace').strip('\x00'): hashlib.sha256(s.get_data()).hexdigest()
                    for s in pe.sections}
        comparison.append(dict(file=path.relative_to(ROOT).as_posix(), bytes=len(data),
                               sha256=hashlib.sha256(data).hexdigest(), sections=sections))
        pe.close()
    (OUT / 'opengl_reference_comparison.json').write_text(json.dumps(comparison, indent=2), encoding='utf-8')
    component_map = json.loads((ROOT / 'report/NEKOZZZ_BINARY_COMPONENT_MAP.json').read_text(encoding='utf-8'))
    vc = [x for x in component_map['file_evidence'] if x['component'] == 'Microsoft VC runtime']
    (OUT / 'vc_runtime_files.json').write_text(json.dumps(vc, indent=2), encoding='utf-8')
    print(len(headers), 'Qt source SPDX headers;', len(attributions), 'attribution records;', len(vc), 'VC files')


if __name__ == '__main__':
    main()
