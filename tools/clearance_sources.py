"""Acquire unmodified exact-version upstream evidence; never install packages."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'report' / 'clearance_sources'


def fetch(url, name):
    target = OUT / name
    if not target.exists():
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read()
        target.write_bytes(data)
    data = target.read_bytes()
    return dict(filename=name, url=url, bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                status='acquired; binary correspondence requires review')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    requests = [
        ('https://www.python.org/ftp/python/3.14.7/Python-3.14.7.tar.xz', 'Python-3.14.7.tar.xz'),
        ('https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/pyside-setup-everywhere-src-6.11.2.tar.xz', 'pyside-setup-everywhere-src-6.11.2.tar.xz'),
        ('https://download.qt.io/official_releases/qt/6.11/6.11.2/submodules/qtbase-everywhere-src-6.11.2.tar.xz', 'qtbase-everywhere-src-6.11.2.tar.xz'),
        ('https://download.qt.io/official_releases/qt/6.11/6.11.2/submodules/qttools-everywhere-src-6.11.2.tar.xz', 'qttools-everywhere-src-6.11.2.tar.xz'),
        ('https://download.qt.io/official_releases/qt/6.11/6.11.2/submodules/qtsvg-everywhere-src-6.11.2.tar.xz', 'qtsvg-everywhere-src-6.11.2.tar.xz'),
        ('https://download.qt.io/official_releases/qt/6.11/6.11.2/submodules/qtimageformats-everywhere-src-6.11.2.tar.xz', 'qtimageformats-everywhere-src-6.11.2.tar.xz'),
    ]
    for package, version in [('PyMuPDF', '1.28.2'), ('lxml', '6.1.3')]:
        try:
            record = fetch(f'https://pypi.org/pypi/{package}/{version}/json', f'{package}-{version}-pypi.json')
            records.append(record)
            metadata = json.loads((OUT / record['filename']).read_bytes())
            for item in metadata['urls']:
                if item['packagetype'] == 'sdist':
                    requests.append((item['url'], item['filename']))
        except Exception as error:
            records.append(dict(component=package, status='FAILED', error=str(error)))
    for url, name in requests:
        try:
            record = fetch(url, name)
            records.append(record)
            print(name, record['bytes'], flush=True)
        except Exception as error:
            records.append(dict(filename=name, url=url, status='FAILED', error=str(error)))
            print(name, 'FAILED', str(error), flush=True)
        (OUT / 'manifest.json').write_text(json.dumps(records, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
