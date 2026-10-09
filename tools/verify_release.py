"""Read-only ZIP/source/Git verifier used by publish_github.ps1 (stdlib only)."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_config(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    assert re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', config['version']), 'Invalid version'
    assert config['tag'] == 'v' + config['version'], 'Tag/version mismatch'
    assert re.fullmatch(r'[\w.-]+/[\w.-]+', config['repo']), 'Invalid repository'
    root = (path.parent / config.get('asset_root', '.')).resolve()
    return path, config, root


def asset_path(root, name):
    assert Path(name).name == name and '/' not in name and '\\' not in name, 'Unsafe asset name'
    return root / name


def safe_zip(archive):
    names = set()
    total = 0
    entries = archive.infolist()
    assert len(entries) <= 100000, 'ZIP entry limit'
    for entry in entries:
        name = entry.filename
        parts = PurePosixPath(name).parts
        assert name and '\\' not in name and ':' not in name and not name.startswith('/') and '..' not in parts, 'Unsafe ZIP path'
        assert name.casefold() not in names, 'Duplicate ZIP path'
        assert (entry.external_attr >> 16) & 0o170000 != 0o120000, 'ZIP symlink'
        names.add(name.casefold())
        total += entry.file_size
        assert entry.file_size <= 8 * 1024**3 and total <= 32 * 1024**3, 'ZIP size limit'
    assert archive.testzip() is None, 'ZIP CRC failure'


def validate_local(config_path):
    path, config, root = load_config(config_path)
    assets = []
    by_role = {}
    for item in config['assets']:
        name = item['name']
        assert name not in {a['name'] for a in assets}, 'Duplicate asset'
        file = asset_path(root, name)
        assert file.is_file() and not file.is_symlink(), 'Missing asset: ' + name
        actual = digest(file)
        assert actual == item['sha256'], 'Asset SHA256 mismatch: ' + name
        assets.append(dict(name=name, sha256=actual, bytes=file.stat().st_size, role=item['role']))
        assert item['role'] not in by_role, 'Duplicate role'
        by_role[item['role']] = file
    for role in ('binary', 'source', 'corresponding_source', 'checksums', 'notes', 'audit'):
        assert role in by_role, 'Missing delivery role: ' + role
    for role in ('binary', 'source', 'corresponding_source'):
        with zipfile.ZipFile(by_role[role]) as archive:
            safe_zip(archive)
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                n = PurePosixPath(entry.filename)
                assert n.suffix.lower() not in ('.db', '.sqlite', '.sqlite3', '.accdb', '.mdb', '.pem', '.key'), 'Private data member'
                assert n.name != 'settings.json', 'Personal settings member'
    checksums = {}
    for line in by_role['checksums'].read_text(encoding='utf-8-sig').splitlines():
        match = re.fullmatch(r'([0-9a-fA-F]{64})  (.+)', line)
        assert match and match[2] not in checksums, 'Invalid checksums'
        checksums[match[2]] = match[1].lower()
    expected_sums = {a['name']:a['sha256'] for a in assets if a['role'] != 'checksums'}
    assert checksums == expected_sums, 'Checksums do not cover exactly all other attachments'
    notes = by_role['notes'].read_text(encoding='utf-8-sig')
    assert config['tag'] in notes and notes.strip(), 'Notes missing target version'
    manifest_file = (path.parent / config['source_manifest']).resolve()
    assert digest(manifest_file) == config['source_manifest_sha256'], 'Source manifest changed'
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    with zipfile.ZipFile(by_role['source']) as source, zipfile.ZipFile(by_role['binary']) as binary, zipfile.ZipFile(by_role['corresponding_source']) as upstream:
        source_files = {i.filename.removeprefix('source/'):i for i in source.infolist() if not i.is_dir()}
        assert set(source_files) == set(manifest), 'Source ZIP file set differs from RC manifest'
        for name, record in manifest.items():
            data = source.read(source_files[name])
            assert hashlib.sha256(data).hexdigest() == record['sha256'] and len(data) == record['bytes'], 'Source member mismatch: ' + name
        version = source.read('source/version.py').decode('utf-8')
        assert re.search(r"APP_VERSION\s*=\s*['\"]" + re.escape(config['version']) + r"['\"]", version), 'Source version mismatch'
        assert re.search(r'DB_SCHEMA_VERSION\s*=\s*' + str(config['db_schema_version']) + r'\b', version)
        assert re.search(r'BACKUP_FORMAT_VERSION\s*=\s*' + str(config['backup_format_version']) + r'\b', version)
        members = set(binary.namelist())
        prefix = config.get('binary_prefix', 'Nekozzz/')
        assert hashlib.sha256(binary.read(prefix + 'Nekozzz.exe')).hexdigest() == config['exe_sha256'], 'EXE differs from accepted RC'
        required = ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'SOURCE_AVAILABILITY.md', 'LGPL_REPLACEMENT.md', 'CORRESPONDING_SOURCE_BUILD_GUIDE.md')
        assert all(prefix + n in members for n in required), 'Missing binary compliance companion'
        runtime = [n for n in members if '/licenses/' not in n.lower()]
        forbidden = ('msvcp140', 'vcruntime140', 'vc_redist', 'opengl32sw', 'qt6network', 'qgif.', 'qwebp.', 'qtiff.')
        assert not any(PurePosixPath(n).name.lower().startswith(forbidden) or '/lxml/' in n.lower() for n in runtime), 'Removed runtime component returned'
        assert hashlib.sha256(binary.read(prefix + '_internal/resources/templates/personnel_table.docx')).hexdigest() == config['template_sha256'], 'Template mismatch'
        index = json.loads(source.read('source/SOURCE_DELIVERY_INDEX.json'))
        for entry in index['upstream_archives']:
            member = 'corresponding-source/archives/' + entry['filename']
            with upstream.open(member) as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == entry['sha256'], 'Upstream archive mismatch'
        assert 'corresponding-source/CORRESPONDING_SOURCE_BUILD_GUIDE.md' in upstream.namelist()
    acceptance = config['developer_acceptance']
    assert all(acceptance.get(k) == 'PASS' for k in ('rc_business', 'office', 'company', 'backup', 'access_migration')), 'Manual acceptance incomplete'
    return dict(valid=True, repo=config['repo'], tag=config['tag'], version=config['version'], assets=assets, source_files=len(manifest), config_sha256=digest(path), source_manifest_sha256=digest(manifest_file), source_commit_confirmed=False)


def git(repo, *arguments):
    run = subprocess.run(['git', '-C', str(repo), *arguments], capture_output=True)
    if run.returncode:
        raise RuntimeError(run.stderr.decode('utf-8', errors='replace').strip())
    return run.stdout


def same_source(a, b, name):
    if a == b:
        return 'byte-identical'
    if Path(name).suffix.lower() in ('.py', '.md', '.txt', '.json', '.ps1', '.spec', '.ui', '.gitignore') or name == '.gitignore':
        if a.replace(b'\r\n', b'\n') == b.replace(b'\r\n', b'\n'):
            return 'CRLF/LF-only; Git checkout normalization'
    raise AssertionError('Source differs from accepted archive: ' + name)


def validate_git(config_path, repo, revision=None):
    path, config, root = load_config(config_path)
    repo = Path(repo).resolve()
    git_root = Path(git(repo, 'rev-parse', '--show-toplevel').decode().strip()).resolve()
    assert git_root == repo, 'RepoPath must be repository root'
    head = git(repo, 'rev-parse', 'HEAD').decode().strip()
    branch = git(repo, 'symbolic-ref', '--short', 'HEAD').decode().strip()
    assert branch, 'Detached HEAD'
    origin = git(repo, 'remote', 'get-url', 'origin').decode().strip()
    assert origin.lower() in {('https://github.com/' + config['repo'] + '.git').lower(), ('https://github.com/' + config['repo']).lower(), ('git@github.com:' + config['repo'] + '.git').lower()}, 'Unexpected origin; credentials in URLs forbidden'
    baseline = git(repo, 'rev-parse', config['baseline_tag'] + '^{commit}').decode().strip()
    git(repo, 'merge-base', '--is-ancestor', baseline, revision or head)
    assets = {a['role']:asset_path(root, a['name']) for a in config['assets']}
    rows = {}
    tracked = set(git(repo, 'ls-files', '-z').decode('utf-8').strip('\0').split('\0'))
    reviewed_upstream = set(config.get('allow_ignored_source_files', []))
    if revision:
        for row in git(repo, 'ls-tree', '-r', '-z', revision).split(b'\0'):
            if row:
                meta, name = row.split(b'\t', 1)
                mode, kind, oid = meta.split()
                assert mode not in (b'120000', b'160000'), 'Symlinks/submodules require manual review'
                rows[name.decode('utf-8')] = oid.decode()
    for name in (rows if revision else tracked):
        parts = PurePosixPath(name).parts
        upstream_notice = name in reviewed_upstream and name.startswith('licenses/upstream_sources/') and Path(name).suffix.lower() in ('.png', '.toml')
        assert upstream_notice or not any(part.lower() in ('.venv', 'venv', 'images', 'backups', '__pycache__') for part in parts), 'Private/generated directory tracked'
        assert Path(name).suffix.lower() not in ('.db','.sqlite','.sqlite3','.accdb','.mdb','.pem','.key','.zip','.pyc'), 'Private/generated file tracked'
        assert PurePosixPath(name).name not in ('settings.json','.env'), 'Private settings/credentials tracked'
    comparisons = {}
    doc_overrides = set(config.get('documentation_overrides', []))
    with zipfile.ZipFile(assets['source']) as source:
        files = {i.filename.removeprefix('source/'):i for i in source.infolist() if not i.is_dir()}
        for name, entry in files.items():
            file = repo / name
            assert file.resolve().is_relative_to(repo), 'Unsafe source path'
            if revision:
                assert name in rows, 'Source absent from commit: ' + name
                data = git(repo, 'cat-file', 'blob', rows[name])
            else:
                assert file.is_file() and not file.is_symlink(), 'Missing working source: ' + name
                data = file.read_bytes()
            if name in doc_overrides:
                assert name.endswith('.md'), 'Only Markdown acceptance updates can override snapshot'
                comparisons[name] = 'document-only acceptance/status supplement; snapshot remains unchanged'
            else:
                comparisons[name] = same_source(source.read(entry), data, name)
    # Extra approved publishing/document files are never collected with git add -A.
    approved = set(comparisons) | set(config.get('additional_commit_files', []))
    for name in config.get('additional_commit_files', []):
        assert (name.startswith('tools/') and Path(name).suffix.lower() in ('.py','.ps1')) or ('/' not in name and name.endswith('.md')), 'Unsafe publishing companion path'
        assert (repo/name).is_file() and not (repo/name).is_symlink(), 'Missing publishing companion: ' + name
    change_output = git(repo, 'status', '--porcelain=v1', '-z', '--untracked-files=all').split(b'\0')
    changes = []
    for record in change_output:
        if not record:
            continue
        status, name = record[:2].decode(), record[3:].decode('utf-8')
        assert 'R' not in status and 'C' not in status and 'D' not in status, 'Rename/copy/deletion requires manual review'
        assert name in approved, 'Unreviewed worktree change: ' + name
        assert status[0] in (' ', '?'), 'Existing staged files require developer review'
        changes.append(name)
    ignored_allowed = set(config.get('allow_ignored_source_files', []))
    for name in comparisons:
        if name not in tracked and name not in changes:
            assert name in ignored_allowed, 'Required source ignored by Git: ' + name
            changes.append(name)
    working_files = {}
    for name in approved:
        file = repo / name
        assert file.resolve().is_relative_to(repo), 'Unsafe approved path'
        if file.is_file():
            working_files[name] = digest(file)
    return dict(head=head, branch=branch, origin=origin, baseline_commit=baseline, comparisons=comparisons, commit_files=sorted(changes), approved_worktree_hashes=working_files, source_commit_confirmed=bool(revision))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--repo-path')
    parser.add_argument('--commit')
    args = parser.parse_args()
    result = {'valid':False}
    try:
        result = validate_local(args.config)
        if args.repo_path:
            result['git'] = validate_git(args.config, args.repo_path, args.commit)
            result['source_commit_confirmed'] = bool(args.commit)
    except Exception as error:
        result.update(valid=False, error=str(error))
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Verification:', 'PASS' if result['valid'] else result.get('error'))
    return 0 if result['valid'] else 2


if __name__ == '__main__':
    sys.exit(main())
