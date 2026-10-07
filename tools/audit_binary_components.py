"""Evidence inventory for the existing Windows onedir; never alters the bundle.

Package ownership is based on the build TOC and matching source bytes. Upstream
license summaries are audit notes, not a claim of complete license clearance.
"""
import ast
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import re
import sys
import pefile
from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'dist/Nekozzz'
REPORT = ROOT / 'report'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def toc_records(value):
    if isinstance(value, (tuple, list)):
        if len(value) == 3 and all(isinstance(x, str) for x in value):
            yield value
        else:
            for child in value:
                yield from toc_records(child)


def redact(path):
    text = str(path)
    replacements = [(str(ROOT / '.venv'), '%VENV%'), (str(ROOT), '%PROJECT%'),
                    (sys.base_prefix, '%PYTHON%'),
                    ('C:\\Program Files\\Microsoft\\jdk-17.0.8.7-hotspot', '%MICROSOFT_JDK_17%')]
    for prefix, label in replacements:
        if text.lower().startswith(prefix.lower()):
            return label + text[len(prefix):]
    return re.sub(r'(?i)C:\\Users\\[^\\]+', '%USERPROFILE%', text)


def pe_details(path):
    try:
        pe = pefile.PE(str(path))
    except pefile.PEFormatError:
        return {'pe_status': 'NOT_PE'}
    info = {}
    for group in getattr(pe, 'FileInfo', []):
        for item in group:
            for table in getattr(item, 'StringTable', []):
                info.update({k.decode(errors='replace'): v.decode(errors='replace')
                             for k, v in table.entries.items()})
    imports = [item.dll.decode(errors='replace')
               for item in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', [])]
    delayed = [item.dll.decode(errors='replace')
               for item in getattr(pe, 'DIRECTORY_ENTRY_DELAY_IMPORT', [])]
    machine = hex(pe.FILE_HEADER.Machine)
    pe.close()
    return dict(pe_status='PE', machine=machine, version_metadata=info,
                imports=imports, delayed_imports=delayed)


def identify(relative, source, details):
    name = Path(relative).name.lower()
    origin = source.replace('\\', '/').lower()
    if relative == 'Nekozzz.exe':
        return 'Nekozzz + PyInstaller bootloader / embedded Python archive'
    if name.startswith(('api-ms-', 'vcruntime', 'msvcp')) or name == 'ucrtbase.dll':
        return 'Microsoft API-set/UCRT' if name.startswith('api-ms-') or name == 'ucrtbase.dll' else 'Microsoft VC runtime'
    if name in ('libssl-3.dll', 'libcrypto-3.dll') and origin.startswith(sys.base_prefix.replace('\\', '/').lower()):
        return 'OpenSSL'
    if name == 'libffi-8.dll' and origin.startswith(sys.base_prefix.replace('\\', '/').lower()):
        return 'libffi'
    if name == 'sqlite3.dll' and origin.startswith(sys.base_prefix.replace('\\', '/').lower()):
        return 'SQLite'
    if '/site-packages/pyside6/' in origin:
        if name == 'opengl32sw.dll':
            return 'Qt software OpenGL (Mesa/LLVM strings; exact build unresolved)'
        if name.startswith('qt6'):
            return 'Qt ' + Path(relative).stem[3:]
        if '/plugins/' in origin:
            return 'Qt plugin ' + relative.replace('\\', '/').split('/plugins/', 1)[1]
        return 'PySide6 bindings'
    for marker, component in [('pymupdf/', 'PyMuPDF/MuPDF'), ('pil/', 'Pillow'),
                              ('lxml/', 'lxml'), ('shiboken6/', 'Shiboken6'), ('pythonwin/', 'pywin32'),
                              ('pywin32_system32/', 'pywin32'), ('win32/', 'pywin32'),
                              ('win32com/', 'pywin32'), ('win32comext/', 'pywin32')]:
        if '/site-packages/' + marker in origin:
            return component
    if name.startswith('pyodbc.') and '/site-packages/' in origin:
        return 'pyodbc'
    if origin.startswith(sys.base_prefix.replace('\\', '/').lower()):
        return 'CPython runtime/stdlib'
    if name == 'base_library.zip':
        return 'CPython runtime/stdlib'
    if relative.startswith(('licenses/', '_internal/licenses/')) or name in ('license', 'third_party_notices.md', 'readme.md'):
        return 'Distribution license/documentation resources'
    if relative.startswith(('_internal/resources/', '_internal/ui/', '_internal/access source/')):
        return 'Nekozzz immutable resources (developer provenance recorded separately)'
    if not relative.endswith(('.dll', '.pyd', '.exe', '.so', '.dat')) and source:
        return 'Other build data (TOC source recorded)'
    return 'UNKNOWN / MANUAL REVIEW'


def policy(component):
    required, action, version = True, 'keep', 'UNKNOWN'
    license_name, notice, obligation = 'UNKNOWN', 'MANUAL REVIEW', 'MANUAL REVIEW'
    source = 'Build TOC, installed wheel notices and PE metadata'
    purpose = component
    if component.startswith('Qt plugin ') or component.startswith('Qt '):
        version = metadata.version('PySide6')
        license_name = 'LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only; embedded third-party terms separately'
        source = 'Exact Qt 6.11.2 source archives; report/clearance/qt_source_licenses.json'
        notice = 'Original exact-version module licenses and attribution texts in licenses/upstream_sources; compiled configuration still requires reconciliation'
        obligation = 'Exact corresponding sources/build configuration and LGPL dynamic-library replacement terms'
        if component.startswith('Qt plugin ') and not any(s in component for s in ('qwindows.dll','qjpeg.dll','qico.dll','qmodernwindowsstyle.dll')):
            required = 'unknown'
            purpose = 'Automatically collected plugin; kept pending compatibility/format review, not proved required'
        if 'imageformats/' in component:
            license_name += '; embedded codec versions/attributions are NOT CLEARED'
        if 'VirtualKeyboard' in component or 'qtvirtualkeyboardplugin' in component:
            license_name = 'GPLv3 open-source option (not LGPL); exact 6.11.2 source terms to confirm'
        if 'Pdf' in component or 'qpdf.dll' in component:
            license_name = 'Qt PDF LGPLv3/GPLv2 options plus PDFium/third-party terms; exact source review pending'
        if any(s in component for s in ('VirtualKeyboard','qtvirtualkeyboardplugin','Pdf','qpdf.dll','Qml','Quick')):
            required, action = 'unknown', 'investigate'
        if 'software OpenGL' in component:
            version = 'Embedded strings Mesa 11.2.2 / LLVM 3.6.2; NOT a verified build/source version'
            license_name = 'UNKNOWN exact composite license; Mesa/LLVM attribution review required'
            required, action = True, 'investigate'
            obligation = 'Resolve exact Qt fallback distribution source and all historical Mesa/LLVM notices'
    elif component in ('PySide6 bindings', 'Shiboken6'):
        version = metadata.version('PySide6')
        license_name = 'LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only (installed metadata)'
        notice = 'Original PySide/Shiboken 6.11.2 source licenses acquired; wheel build correspondence not fully established'
        obligation = 'Exact corresponding source and LGPL obligations'
    elif component == 'PyMuPDF/MuPDF':
        version = 'PyMuPDF 1.28.2 / MuPDF 1.28.2 (runtime query, matched native wheel bytes)'
        license_name = 'AGPLv3 / commercial alternative; using open-source option'
        notice = 'Installed COPYING, root AGPL, exact MuPDF 1.28.2 source/dependency notices acquired; wheel build options still require reconciliation'
        source = 'https://github.com/pymupdf/PyMuPDF ; https://github.com/ArtifexSoftware/mupdf'
        obligation = 'Exact binding/native/dependency sources, patches and build scripts; see SOURCE_AVAILABILITY.md'
    elif component == 'Pillow':
        version = metadata.version('Pillow')
        required, action = False, 'investigate'
        license_name = 'MIT-CMU and bundled codec licenses'
        notice = 'Complete installed Pillow LICENSE copied; source/build codecs mapped separately'
        obligation = 'Retain all codec attributions; evaluate optional runtime exclusion only with packaged regression'
    elif component == 'lxml':
        version = metadata.version('lxml')
        license_name = 'BSD-3-Clause + ElementTree/PSF and native library licenses'
        notice = 'Installed LICENSE.txt and LICENSES.txt retained'
        obligation = 'Retain notices; resolve exact native build configuration, including whether iconv is compiled in'
    elif component == 'pyodbc':
        version = metadata.version('pyodbc')
        license_name = 'MIT-0 (actual installed text)'
        notice, obligation = 'Installed LICENSE.txt retained', 'No copyleft source obligation'
    elif component == 'pywin32':
        version = metadata.version('pywin32')
        license_name = 'Component permissive/PSF notices (not one blanket MIT license)'
        notice, obligation = 'Installed win32/com/other notices retained', 'Preserve applicable copyrights/licenses'
    elif component == 'OpenSSL':
        version = '3.5.7 (PE + runtime query)'
        license_name = 'Apache-2.0'
        source = 'https://github.com/openssl/openssl'
        notice = 'Official 3.5.7 LICENSE and observed PE attribution in licenses/native/OpenSSL; root NOTICE HTTP 404, incorporated notices review pending'
        obligation = 'Apache attribution/NOTICE requirements; no copyleft source requirement'
    elif component == 'libffi':
        version = 'CPython v3.14.7 build recipe specifies 3.4.4; binary tag/hash correspondence not yet verified'
        license_name = 'MIT'
        notice = 'Copyright and full permission/disclaimer in licenses/CPython/LICENSE.txt'
        obligation = 'Retain notice; exact upstream version unresolved, source origin is CPython DLLs'
        purpose = 'ctypes / Word COM / Windows integrations'
    elif component == 'SQLite':
        version = '3.50.4 (PE and runtime)'
        license_name, notice = 'Public domain', 'Status/blessing linked in THIRD_PARTY_NOTICES.md'
        source, obligation = 'https://sqlite.org/copyright.html', 'No traditional copyleft source requirement'
    elif component == 'CPython runtime/stdlib':
        version = sys.version.split()[0]
        license_name = 'PSF-2.0 and historical/embedded third-party licenses'
        notice = 'Full interpreter LICENSE.txt retained; additional bundled library review in report'
        obligation = 'Retain PSF and native third-party notices; do not treat all stdlib files as separate packages'
    elif component.startswith('Microsoft'):
        required, action = 'unknown', 'investigate'
        license_name = 'Microsoft proprietary redistribution terms — NOT CLEARED'
        source = 'https://learn.microsoft.com/en-us/cpp/windows/determining-which-dlls-to-redistribute?view=msvc-170'
        notice = 'BLOCKER: entitlement and exact redistribution grant not established from local copies'
        obligation = 'Resolve REDIST/license entitlement, approved provenance and supported Windows deployment policy'
    elif component.startswith('Nekozzz +'):
        version = 'Nekozzz 0.9.2 / PyInstaller ' + metadata.version('PyInstaller')
        license_name = 'AGPL-3.0-only + GPL-2.0-or-later WITH bootloader exception; hook terms separately'
        notice = 'Root LICENSE, PyInstaller COPYING and hooks-contrib LICENSE retained'
        obligation = 'Application corresponding source; preserve bootloader/runtime hook notices'
    elif component.startswith('Nekozzz immutable'):
        version, license_name = '0.9.2', 'Developer provenance; historical table format rights unresolved'
        obligation = 'Resource facts in final audit; do not assert ownership of original public tender format'
        notice = 'Resource provenance recorded in final audit'
    elif component.startswith('Distribution'):
        version, license_name = 'See component notices', 'Individual documents retain their own terms'
        notice, obligation = 'Bundled accessible text', 'No blanket replacement license'
    else:
        required, action = 'unknown', 'investigate'
    return dict(version=version, purpose=purpose, required_by_nekozzz=required,
                direct_or_transitive='direct application' if component.startswith('Nekozzz') else 'transitive / packaged runtime',
                license=license_name, license_source=source, notice_status=notice,
                source_obligation=obligation, redistribution_notes='No clearance inferred from package presence', action=action)


def audit():
    analysis = ast.literal_eval((ROOT/'build/Nekozzz/Analysis-00.toc').read_text(encoding='utf-8'))
    records = list(toc_records(analysis))
    origins = {dest.replace('\\', '/'): source for dest, source, kind in records if kind in ('BINARY','EXTENSION','DATA')}
    inventory, files, components = [], [], {}
    for path in sorted(BUNDLE.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(BUNDLE).as_posix()
        item = dict(path=relative, bytes=path.stat().st_size, sha256=digest(path))
        inventory.append(item)
        source = origins.get(relative.removeprefix('_internal/'), '')
        native = path.suffix.lower() in ('.dll','.pyd','.exe','.so','.dat') or path.read_bytes()[:2] == b'MZ'
        details = pe_details(path) if native else {}
        component = identify(relative, source, details)
        info = dict(item, component=component, native_or_blob=native,
                    build_source=redact(source) if source else 'NOT_IN_BINARY/DATA_TOC',
                    source_sha256_match=bool(source and Path(source).is_file() and digest(Path(source))==item['sha256']),
                    **details)
        files.append(info)
        group = components.setdefault(component, dict(component=component, files=[], **policy(component), evidence=[]))
        group['files'].append(relative)
        if source:
            group['evidence'].append(dict(file=relative, source=redact(source), source_sha256_match=info['source_sha256_match']))
    source_imports = {}
    for folder in ('gui','services'):
        for path in (ROOT/folder).rglob('*.py'):
            for module in re.findall(r'(?:from|import)\s+(PySide6\.\w+)',path.read_text(encoding='utf-8')):
                source_imports.setdefault(module,[]).append(path.relative_to(ROOT).as_posix())
    archive = CArchiveReader(str(BUNDLE/'Nekozzz.exe'))
    archive_modules = sorted(archive.open_embedded_archive('PYZ.pyz').toc)
    for package, license_name in [('openpyxl','MIT'),('et_xmlfile','MIT')]:
        modules = [m for m in archive_modules if m==package or m.startswith(package+'.')]
        if modules:
            components[package] = dict(component=package, version=metadata.version(package), files=['Nekozzz.exe::PYZ.pyz'],
                purpose='Spreadsheet export and schema workbook reading', required_by_nekozzz=True,
                direct_or_transitive='direct' if package=='openpyxl' else 'transitive',
                license=license_name,license_source='Installed distribution metadata and license',
                notice_status=f'licenses/{package}/ original installed license present',
                source_obligation='Retain license/copyright, no copyleft source obligation',
                redistribution_notes='Embedded pure Python, no standalone DLL',action='keep',evidence=modules)
    hooks = []
    scripts = {dest: source for dest, source, kind in records if kind=='PYSOURCE'}
    for name in archive.toc:
        if not name.startswith('pyi_rth'):
            continue
        origin = scripts.get(name,'')
        header = Path(origin).read_text(encoding='utf-8')[:1500] if Path(origin).is_file() else ''
        spdx = re.search(r'SPDX-License-Identifier:\s*([^\r\n]+)', header)
        hooks.append(dict(name=name, build_source=redact(origin),
                          license=spdx.group(1).strip() if spdx else 'UNKNOWN: inspect source header',
                          evidence='Embedded EXE CArchive entry, Analysis PYSOURCE record, exact installed source SPDX header'))
    baseline = json.loads((REPORT/'NEKOZZZ_BINARY_INVENTORY_PRE_FINAL.json').read_text(encoding='utf-8'))
    before = {p['path'].replace('\\','/'): p for p in baseline}
    now = {p['path']: p for p in inventory}
    diff = dict(removed=sorted(set(before)-set(now)),added=sorted(set(now)-set(before)),
                changed=sorted(p for p in set(before)&set(now) if before[p]['sha256']!=now[p]['sha256']))
    result = dict(status='NOT READY — LICENSE BLOCKERS REMAIN',
                  build_baseline=dict(python_environment=sys.version,pyinstaller=metadata.version('PyInstaller'),
                                      pyside6=metadata.version('PySide6'),architecture='AMD64 PE 0x8664',format='onedir'),
                  counts=dict(files=len(inventory),dlls=sum(p['path'].endswith('.dll') for p in inventory),
                              native_or_blob=sum(p['native_or_blob'] for p in files),bytes=sum(p['bytes'] for p in inventory)),
                  inventory_diff=diff,qt_source_imports=source_imports,runtime_hooks=hooks,
                  embedded_python_modules=archive_modules,
                  components=list(components.values()),file_evidence=files,
                  limitations=['Static imports do not prove dynamic/plugin usage or full third-party attribution',
                               'Package hashes establish installed provenance, not complete rebuildable source',
                               'Exact codec sources, Microsoft entitlement and Qt/MuPDF notices remain blockers'])
    (REPORT/'NEKOZZZ_BINARY_INVENTORY.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
    (REPORT/'NEKOZZZ_BINARY_COMPONENT_MAP.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    lines = ['# Nekozzz 0.9.2 Binary Component Map', '', 'Status: **NOT READY — BLOCKERS REMAIN**', '',
             'Evidence: build Analysis TOC, source/bundle hash comparison, PE version/import tables, EXE CArchive/PYZ.',
             'Exact file lists, hashes, PE imports and observed origins are in the JSON companion.', '',
             '## Components', '', '| Component | Files | Version | Required | License | Action |', '|---|---:|---|---|---|---|']
    for c in components.values():
        lines.append(f"| {c['component']} | {len(c['files'])} | {c['version']} | {c['required_by_nekozzz']} | {c['license']} | {c['action']} |")
    lines += ['', '## Direct Qt source imports', '']
    for module, paths in sorted(source_imports.items()):
        lines.append(f'- {module}: '+', '.join(paths))
    lines += ['', '## Inventory diff', '', '```json',json.dumps(diff,indent=2),'```','',
              '## File evidence', '', '| File | Component | PE version | Provenance hash match |', '|---|---|---|---|']
    for p in files:
        if p['native_or_blob']:
            ver=p.get('version_metadata',{}).get('FileVersion','UNKNOWN')
            lines.append(f"| {p['path']} | {p['component']} | {ver} | {p['source_sha256_match']} |")
    (REPORT/'NEKOZZZ_BINARY_COMPONENT_MAP.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Audit counts:',result['counts'])
    print('UNKNOWN native files:',[p['path'] for p in files if p['native_or_blob'] and p['component'].startswith('UNKNOWN')])


if __name__ == '__main__':
    audit()
