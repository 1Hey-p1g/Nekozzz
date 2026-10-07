"""Isolated, repeatable pruning builds and evidence. No application code changes."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'report/pruning'
PYTHON = ROOT / '.venv/Scripts/python.exe'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(bundle, destination, work=None):
    from PyInstaller.archive.readers import CArchiveReader
    import pefile
    rows = []
    for path in sorted(bundle.rglob('*')):
        if not path.is_file():
            continue
        row = dict(path=path.relative_to(bundle).as_posix(), bytes=path.stat().st_size, sha256=sha(path))
        if path.suffix.lower() in ('.dll', '.pyd', '.exe'):
            pe = pefile.PE(str(path))
            row['imports'] = [i.dll.decode() for i in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', [])]
            row['delay_imports'] = [i.dll.decode() for i in getattr(pe, 'DIRECTORY_ENTRY_DELAY_IMPORT', [])]
            row['machine'] = hex(pe.FILE_HEADER.Machine)
            pe.close()
        rows.append(row)
    archive = CArchiveReader(str(bundle / 'Nekozzz.exe'))
    result = dict(counts=dict(files=len(rows), dlls=sum(r['path'].lower().endswith('.dll') for r in rows),
                              bytes=sum(r['bytes'] for r in rows)), files=rows,
                  pyz=sorted(archive.open_embedded_archive('PYZ.pyz').toc))
    if work:
        from tools.audit_binary_components import toc_records, redact
        records = list(toc_records(ast.literal_eval((work / 'Nekozzz/Analysis-00.toc').read_text(encoding='utf-8'))))
        result['sources'] = [dict(destination=d, source=redact(s), kind=k)
                             for d, s, k in records if k in ('BINARY', 'EXTENSION', 'PYSOURCE')]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(result['counts'])
    return result


def notices(bundle):
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'SOURCE_AVAILABILITY.md'):
        shutil.copy2(ROOT / name, bundle / name)
    shutil.copytree(ROOT / 'licenses', bundle / 'licenses', dirs_exist_ok=True)
    shutil.copy2(ROOT / 'BUILD_WINDOWS.md', bundle / 'README.md')


def build(name, group, probe=False):
    target = name + ('_probe' if probe else '')
    folder = ROOT / 'build/prune_experiments' / target
    folder.mkdir(parents=True, exist_ok=True)
    spec = (ROOT / 'Nekozzz.spec').read_text(encoding='utf-8')
    spec = spec.replace('root = Path(SPECPATH)', 'root = Path(' + repr(str(ROOT)) + ')')
    hooks = folder / 'hooks'
    hooks.mkdir(exist_ok=True)
    omitted = {1: 'qtvirtualkeyboardplugin.dll', 2: 'qpdf.dll'}.get(group)
    if omitted:
        # Filter the plugin at QtGui collection time, before recursive bindepend.
        formal_hook = ROOT / 'tools/pyinstaller_hooks/hook-PySide6.QtGui.py'
        source = formal_hook.read_text(encoding='utf-8') if formal_hook.is_file() else (
            "from pathlib import Path\nfrom PyInstaller.utils.hooks.qt import add_qt6_dependencies\n"
            "hiddenimports, binaries, datas = add_qt6_dependencies(__file__)\n")
        source += f"\nbinaries = [(src, dst) for src, dst in binaries if Path(src).name.lower() != {omitted!r}]\n"
        (hooks / 'hook-PySide6.QtGui.py').write_text(source, encoding='utf-8')
        spec = spec.replace("hookspath=[str(root/'tools/pyinstaller_hooks')]", 'hookspath=[' + repr(str(hooks)) + ']')
        spec = spec.replace('hookspath=[]', 'hookspath=[' + repr(str(hooks)) + ']')
    if group == 3:
        spec = spec.replace("excludes=['pytest']", "excludes=['pytest', 'PIL']")
    if probe:
        spec = spec.replace('runtime_hooks=[]', 'runtime_hooks=[' + repr(str(ROOT / 'tools/pruning_probe_hook.py')) + ']')
    specpath = folder / 'Nekozzz.spec'
    specpath.write_text(spec, encoding='utf-8')
    env = os.environ.copy()
    original_path = env.get('PATH', '')
    removed_paths = []
    if group == 4:
        removed_paths = [p for p in original_path.split(os.pathsep) if 'jdk-17.0.8.7-hotspot' in p.lower()]
        env['PATH'] = os.pathsep.join(p for p in original_path.split(os.pathsep) if p not in removed_paths)
    dist = ROOT / 'dist/prune_experiments' / target
    command = [str(PYTHON), '-B', '-m', 'PyInstaller', '--clean', '--noconfirm',
               '--workpath', str(folder / 'work'), '--distpath', str(dist), str(specpath)]
    REPORT.mkdir(parents=True, exist_ok=True)
    with (REPORT / (target + '_build.log')).open('w', encoding='utf-8') as stream:
        run = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    (REPORT / (target + '_build.json')).write_text(json.dumps(dict(command=command, returncode=run.returncode,
        group=group, diagnostic_probe=probe, removed_path_entries=removed_paths), indent=2), encoding='utf-8')
    if run.returncode:
        raise RuntimeError(f'Build failed; see {target}_build.log')
    bundle = dist / 'Nekozzz'
    notices(bundle)
    snapshot(bundle, REPORT / (target + '_inventory.json'), folder / 'work')


def smoke(name):
    """Run the instrumented twin in an isolated temporary portable root."""
    import tempfile
    target = name + '_probe'
    source = ROOT / 'dist/prune_experiments' / target / 'Nekozzz'
    with tempfile.TemporaryDirectory(prefix='Nekozzz_pruning_') as temporary:
        bundle = Path(temporary) / 'app'
        shutil.copytree(source, bundle)
        env = os.environ.copy()
        # No external Python/Qt/plugin directories or JDK fallback in smoke PATH.
        env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32') + os.pathsep + os.environ['SystemRoot']
        for key in ('PYTHONPATH', 'PYTHONHOME', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'QT_IM_MODULE'):
            env.pop(key, None)
        output = REPORT / (name + '_packaged_smoke.json')
        env['NEKOZZZ_PRUNE_PROBE'] = str(ROOT / 'tools/pruning_packaged_probe.py')
        env['NEKOZZZ_PRUNE_RESULT'] = str(output)
        env['NEKOZZZ_PRUNE_ICO'] = str(ROOT / 'resources/icon.ico')
        # Use the real Windows qwindows plugin, not offscreen.
        env['QT_QPA_PLATFORM'] = 'windows'
        with (REPORT / (name + '_packaged_stderr.log')).open('w', encoding='utf-8') as stream:
            run = subprocess.run([str(bundle / 'Nekozzz.exe')], env=env, cwd=temporary,
                                 stdout=stream, stderr=stream, timeout=120)
        print('packaged exit:', run.returncode)
        if not output.is_file():
            raise RuntimeError('Probe did not produce a result')
        result = json.loads(output.read_text(encoding='utf-8'))
        print(json.dumps(result, ensure_ascii=False))
        if run.returncode or result['status'] != 'PASS':
            raise RuntimeError('Packaged probe failed')


def startup(name):
    """Uninstrumented candidate, normal first launch; only own TEMP process."""
    import tempfile
    import time
    import sqlite3
    source = ROOT / 'dist/Nekozzz' if name == 'final' else ROOT / 'dist/prune_experiments' / name / 'Nekozzz'
    with tempfile.TemporaryDirectory(prefix='Nekozzz_plain_startup_') as temporary:
        bundle = Path(temporary) / 'app'
        shutil.copytree(source, bundle)
        env = os.environ.copy()
        env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32') + os.pathsep + os.environ['SystemRoot']
        for key in ('PYTHONPATH', 'PYTHONHOME', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'QT_IM_MODULE',
                    'NEKOZZZ_PRUNE_PROBE', 'NEKOZZZ_PRUNE_RESULT'):
            env.pop(key, None)
        env['QT_QPA_PLATFORM'] = 'windows'
        with (REPORT / (name + '_startup_stderr.log')).open('w', encoding='utf-8') as stream:
            process = subprocess.Popen([str(bundle / 'Nekozzz.exe')], env=env, cwd=temporary, stdout=stream, stderr=stream)
            try:
                time.sleep(5)
                db = bundle / 'database/TenderSystem-v1.db'
                result = dict(running=process.poll() is None, default_database_created=db.is_file(),
                              diagnostic_hook=False, platform='windows', runtime_path='System32 + Windows only')
                if db.is_file():
                    with sqlite3.connect(db.as_uri() + '?mode=ro&immutable=1', uri=True) as connection:
                        result['schema'] = connection.execute('PRAGMA user_version').fetchone()[0]
                    connection.close()
                result['status'] = 'PASS' if result['running'] and result.get('schema') == 1 else 'FAIL'
                (REPORT / (name + '_startup.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
                print(result)
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=20)


def formal(name):
    """Authorized preservation of old installation, then a clean formal build.

Does not invoke ICO conversion or license collection. Existing data is moved
intact with the old installation, never deleted or mixed into a clean bundle.
"""
    auth = json.loads((REPORT / 'formal_rebuild_authorization.json').read_text())
    if not auth.get('preserve_previous_installation_then_rebuild'):
        raise RuntimeError('Missing developer authorization to preserve/rebuild dist')
    source = (ROOT / 'dist/Nekozzz').resolve()
    backup = (ROOT / 'build/prune_experiments' / ('formal_previous_' + name) / 'Nekozzz').resolve()
    for path in (source, backup):
        if not path.is_relative_to(ROOT.resolve()):
            raise RuntimeError('Target outside workspace')
    if source != (ROOT / 'dist/Nekozzz').resolve() or backup.exists():
        raise RuntimeError('Unexpected source or existing backup')
    if source.exists():
        hashes = {p.relative_to(source).as_posix(): sha(p) for p in source.rglob('*') if p.is_file()}
        backup.parent.mkdir(parents=True, exist_ok=True)
        source.rename(backup)
        preserved = all(sha(backup / p) == value for p, value in hashes.items())
        (REPORT / (name + '_preserved_installation.json')).write_text(json.dumps(dict(
            backup=backup.relative_to(ROOT).as_posix(), files=len(hashes), all_hashes_preserved=preserved,
            preserved_data_files=[p for p in hashes if p.startswith(('database/', 'Images/', 'config/', 'Backups/'))]),
            indent=2), encoding='utf-8')
        if not preserved:
            raise RuntimeError('Preservation verification failed')
    env = os.environ.copy()
    envfile = ROOT / 'tools/build_pyinstaller_environment.py'
    if envfile.is_file():
        from tools.build_pyinstaller_environment import build_environment
        env = build_environment(env)
    command = [str(PYTHON), '-B', '-m', 'PyInstaller', '--clean', '--noconfirm', str(ROOT / 'Nekozzz.spec')]
    with (REPORT / (name + '_formal_build.log')).open('w', encoding='utf-8') as stream:
        run = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if run.returncode:
        raise RuntimeError('Formal build failed; intact previous installation remains in backup')
    notices(source)
    for folder in ('database', 'Images', 'config', 'Backups'):
        (source / folder).mkdir(exist_ok=True)
    snapshot(source, REPORT / (name + '_formal_inventory.json'), ROOT / 'build')


def equivalence(name):
    normal = json.loads((REPORT / (name + '_inventory.json')).read_text(encoding='utf-8'))
    probe = json.loads((REPORT / (name + '_probe_inventory.json')).read_text(encoding='utf-8'))
    a = {p['path']: p['sha256'] for p in normal['files'] if p['path'].endswith(('.dll', '.pyd'))}
    b = {p['path']: p['sha256'] for p in probe['files'] if p['path'].endswith(('.dll', '.pyd'))}
    result = dict(all_native_payloads_identical=a == b, native_count=len(a),
                  pyz_additions=sorted(set(probe['pyz']) - set(normal['pyz'])),
                  pyz_removals=sorted(set(normal['pyz']) - set(probe['pyz'])))
    (REPORT / (name + '_probe_equivalence.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(result)
    if a != b or result['pyz_additions'] or result['pyz_removals']:
        raise RuntimeError('Diagnostic twin not equivalent')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('build', 'smoke', 'snapshot', 'startup', 'formal', 'equivalence'))
    parser.add_argument('name')
    parser.add_argument('--group', type=int, default=0)
    parser.add_argument('--probe', action='store_true')
    args = parser.parse_args()
    if args.action == 'build':
        build(args.name, args.group, args.probe)
    elif args.action == 'smoke':
        smoke(args.name)
    elif args.action == 'startup':
        startup(args.name)
    elif args.action == 'formal':
        formal(args.name)
    elif args.action == 'equivalence':
        equivalence(args.name)
    else:
        snapshot(ROOT / 'dist/Nekozzz', REPORT / (args.name + '_inventory.json'), ROOT / 'build')
