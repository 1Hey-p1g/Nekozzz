"""Copy installed notices without changing their content or dependency versions.

This is a preparation set, not proof of final bundle compliance. Run with the
same Python environment used to build the binary; review the manifest afterward.
"""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = (
    'PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6',
    'pyodbc', 'openpyxl', 'et_xmlfile', 'PyMuPDF', 'pywin32', 'lxml',
    'PyInstaller', 'pyinstaller-hooks-contrib', 'Pillow', 'altgraph',
    'packaging', 'pefile', 'pywin32-ctypes', 'setuptools',
)


def scopes(name):
    if name in ('PyInstaller', 'pyinstaller-hooks-contrib'):
        return ['build', 'binary-runtime-bootloader-or-hooks']
    if name == 'Pillow':
        return ['build/test-only; absent from pruned runtime']
    if name in ('altgraph', 'packaging', 'pefile', 'pywin32-ctypes', 'setuptools'):
        return ['build-only; absent from final PYZ']
    return ['runtime']


def collect():
    output = ROOT / 'licenses'
    manifest = []
    for name in PACKAGES:
        dist = metadata.distribution(name)
        for file in dist.files or ():
            if not any(word in Path(str(file)).name.lower()
                       for word in ('license', 'licence', 'copying', 'copyright')):
                continue
            source = Path(dist.locate_file(file))
            if not source.is_file():
                continue
            relative = Path(str(file))
            if relative.is_absolute() or '..' in relative.parts:
                continue
            target = output / name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            data = source.read_bytes()
            target.write_bytes(data)
            manifest.append(dict(package=name, version=dist.version,
                                 scopes=scopes(name),
                                 installed_relative_path=str(file),
                                 notice=str(target.relative_to(ROOT)),
                                 sha256=hashlib.sha256(data).hexdigest()))
    source = Path(sys.base_prefix) / 'LICENSE.txt'
    target = output / 'CPython' / 'LICENSE.txt'
    target.parent.mkdir(parents=True, exist_ok=True)
    data = source.read_bytes()
    target.write_bytes(data)
    manifest.append(dict(package='CPython', version=sys.version.split()[0],
                         scopes=['runtime'],
                         notice=str(target.relative_to(ROOT)),
                         sha256=hashlib.sha256(data).hexdigest()))
    known = {item['notice'] for item in manifest}
    for target in sorted(output.rglob('*')):
        if not target.is_file() or target.name == 'manifest.json':
            continue
        relative = str(target.relative_to(ROOT))
        if relative in known:
            continue
        manifest.append(dict(package='Supplemental upstream evidence',
                             scopes=['supplemental; see notice index for component'],
                             notice=relative, sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Collected {len(manifest)} notices; final native component audit still required.')


if __name__ == '__main__':
    collect()
