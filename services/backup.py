"""Full Backup V1, validated staging and rollback of ordinary restore failures.

The GUI must exclude user operations and exit after restore. File replacement is
not a crash-atomic transaction across SQLite/Images/settings. Safety ZIP and the
rollback directory remain available if replacement/rollback is interrupted.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import uuid
import zipfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from config.paths import DATA_ROOT, resolve_image_path
from database.initializer import publish_staging
from database.runtime import runtime_connection, runtime_maintenance, validate_runtime_path
from migration.migration_validator import validate_target_structure
from migration.target_schema import IMAGE_GROUPS
from version import APP_NAME, APP_VERSION, DB_SCHEMA_VERSION, BACKUP_FORMAT_VERSION


DATABASE_ENTRY = 'database/tender.db'
SETTINGS_ENTRY = 'config/settings.json'
# Resource ceilings, checked before extraction (not a change to Backup V1).
MAX_ARCHIVE_ENTRIES = 100_000
MAX_MEMBER_BYTES = 8 * 1024 ** 3
MAX_EXTRACTED_BYTES = 32 * 1024 ** 3


class BackupValidationError(ValueError):
    pass


class RestoreError(RuntimeError):
    pass


class RestoreRecoveryRequiredError(RestoreError):
    """Automatic rollback was incomplete; stop using live data until recovered."""


@dataclass(frozen=True)
class BackupInfo:
    manifest: dict
    sha256: str
    missing_images: tuple[str, ...] = ()


@dataclass(frozen=True)
class RestoreResult:
    safety_backup: Path
    settings_restored: bool


def _digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def new_output_path(path):
    target = Path(path).expanduser().resolve()
    if target.exists() or Path(path).is_symlink():
        raise FileExistsError(f'目标文件已存在，请另选文件名：{target}')
    if not target.parent.is_dir():
        raise FileNotFoundError(f'目标目录不存在：{target.parent}')
    return target


def publish_file(target, writer):
    """Write beside the destination and publish atomically without overwriting."""
    target = new_output_path(target)
    descriptor, name = tempfile.mkstemp(prefix=f'.{target.name}.', suffix='.tmp', dir=target.parent)
    os.close(descriptor)
    stage = Path(name)
    try:
        writer(stage)
        with stage.open('rb+') as stream:
            os.fsync(stream.fileno())
        publish_staging(stage, target)
    finally:
        stage.unlink(missing_ok=True)
    return target


def _validate_database(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        connection.execute('PRAGMA foreign_keys=ON')
        validate_target_structure(connection)
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise BackupValidationError('备份 SQLite 完整性检查失败')


def _validate_attachment_paths(database, data_root):
    missing = set()
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        for table in IMAGE_GROUPS:
            for (value,) in connection.execute(f'SELECT "路径" FROM "{table}"'):
                if value in (None, ''):
                    continue
                try:
                    path = resolve_image_path(value, data_root=data_root)
                except (TypeError, ValueError) as error:
                    raise BackupValidationError(f'备份附件引用路径不安全：{value!r}') from error
                if not path.is_file():
                    missing.add(value)
    return tuple(sorted(missing))


def _member_path(info):
    name = info.filename
    parts = name.rstrip('/').split('/')
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
    if (not name or '\\' in name or name.startswith('/') or
        any(part in ('', '.', '..') or ':' in part or part.endswith((' ', '.')) or
            any(ord(char) < 32 or char in '<>"|?*' for char in part) or
            part.split('.')[0].upper() in reserved for part in parts)):
        raise BackupValidationError(f'不安全的 ZIP 路径：{name!r}')
    mode = info.external_attr >> 16
    if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
        raise BackupValidationError(f'ZIP 不允许链接或特殊文件：{name}')
    if not (name in ('backup.json', DATABASE_ENTRY, SETTINGS_ENTRY, 'database/', 'config/', 'Images/') or
            name.startswith('Images/')):
        raise BackupValidationError(f'备份含未知路径：{name}')
    return PurePosixPath(name)


class BackupService:
    def __init__(self, database_path, *, data_root=DATA_ROOT, settings_path=None):
        if Path(database_path).is_symlink():
            raise ValueError('数据库不能是链接')
        self.database_path = validate_runtime_path(database_path)
        self.data_root = Path(data_root).resolve()
        self.images = self.data_root / 'Images'
        self.settings = Path(settings_path).absolute() if settings_path is not None else self.data_root / SETTINGS_ENTRY

    def create_backup(self, target_path):
        target = new_output_path(target_path)
        if target.is_relative_to(self.images.resolve()):
            raise ValueError('备份文件不能保存在 Images 内')
        with runtime_maintenance(), tempfile.TemporaryDirectory(prefix='TenderSystem_backup_') as directory:
            snapshot = Path(directory) / 'snapshot.db'
            with runtime_connection(self.database_path) as source, closing(sqlite3.connect(snapshot)) as destination:
                source.backup(destination)
                destination.execute('PRAGMA journal_mode=DELETE')
            _validate_database(snapshot)
            files = {DATABASE_ENTRY: snapshot}
            directories = ['Images/']
            if self.images.is_symlink():
                raise ValueError('Images 不允许为目录链接')
            if self.images.exists():
                if not self.images.is_dir():
                    raise ValueError('Images 必须是目录')
                for path in sorted(self.images.rglob('*')):
                    if path.is_symlink():
                        raise ValueError(f'Images 不允许链接：{path}')
                    if path.is_file():
                        files[path.relative_to(self.data_root).as_posix()] = path
                    elif path.is_dir():
                        directories.append(path.relative_to(self.data_root).as_posix() + '/')
            if self.settings.is_symlink():
                raise ValueError('settings.json 不允许链接')
            if self.settings.exists():
                if not self.settings.is_file():
                    raise ValueError('settings.json 必须是文件')
                files[SETTINGS_ENTRY] = self.settings
            manifest = {
                'format_version': BACKUP_FORMAT_VERSION, 'app_name': APP_NAME,
                'app_version': APP_VERSION, 'database_version': DB_SCHEMA_VERSION,
                'created_at': datetime.now(timezone.utc).isoformat(), 'database_file': DATABASE_ENTRY,
                'includes_images': True, 'includes_settings': SETTINGS_ENTRY in files,
                'files': {name: _digest(path) for name, path in files.items()},
            }
            def write(stage):
                with zipfile.ZipFile(stage, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                    for name in directories:
                        archive.writestr(name, '')
                    for name, path in files.items():
                        archive.write(path, name)
                    archive.writestr('backup.json', json.dumps(manifest, ensure_ascii=False, indent=2))
                # Read every payload back and verify before publishing the ZIP.
                self.inspect_backup(stage)
            return publish_file(target, write)

    def _extract_validated(self, archive_path, staging, expected_digest=None):
        archive_path = Path(archive_path).resolve()
        before = _digest(archive_path)
        if expected_digest is not None and before != expected_digest:
            raise BackupValidationError('备份文件在预览后发生变化，请重新选择并验证')
        try:
            with zipfile.ZipFile(archive_path) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_ARCHIVE_ENTRIES:
                    raise BackupValidationError('备份文件数量超过安全上限')
                if any(entry.file_size > MAX_MEMBER_BYTES for entry in entries):
                    raise BackupValidationError('备份单文件大小超过安全上限')
                if sum(entry.file_size for entry in entries) > MAX_EXTRACTED_BYTES:
                    raise BackupValidationError('备份解压总大小超过安全上限')
                seen = set()
                for entry in entries:
                    _member_path(entry)
                    canonical = entry.filename.rstrip('/').casefold()
                    if canonical in seen:
                        raise BackupValidationError(f'ZIP 含重复路径：{entry.filename}')
                    seen.add(canonical)
                members = {entry.filename: entry for entry in entries if not entry.is_dir()}
                if not any(entry.filename.startswith('Images/') for entry in entries):
                    raise BackupValidationError('备份缺少 Images 结构')
                if 'backup.json' not in members:
                    raise BackupValidationError('备份缺少 backup.json')
                if members['backup.json'].file_size > 16 * 1024 * 1024:
                    raise BackupValidationError('backup.json 过大')
                manifest = json.loads(archive.read('backup.json').decode('utf-8'))
                self._validate_manifest(manifest, members)
                if sum(entry.file_size for entry in entries) > shutil.disk_usage(staging).free:
                    raise BackupValidationError('临时目录可用空间不足以验证此备份')
                for entry in entries:
                    path = staging.joinpath(*_member_path(entry).parts)
                    if entry.is_dir():
                        path.mkdir(parents=True, exist_ok=True)
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(entry) as source, path.open('xb') as output:
                            shutil.copyfileobj(source, output)
                _validate_database(staging / DATABASE_ENTRY)
                inventory = manifest.get('files')
                payload = set(members) - {'backup.json'}
                if not isinstance(inventory, dict) or set(inventory) != payload:
                    raise BackupValidationError('备份文件校验清单缺失或不完整')
                for name, digest in inventory.items():
                    if not isinstance(digest, str) or digest != _digest(staging / name):
                        raise BackupValidationError(f'备份文件校验失败：{name}')
                missing_images = _validate_attachment_paths(staging / DATABASE_ENTRY, staging)
            if _digest(archive_path) != before:
                raise BackupValidationError('备份文件在验证期间发生变化')
            return BackupInfo(manifest, before, missing_images)
        except (zipfile.BadZipFile, sqlite3.Error, KeyError, TypeError, UnicodeError, ValueError) as error:
            if isinstance(error, BackupValidationError):
                raise
            raise BackupValidationError(f'备份验证失败：{error}') from error

    @staticmethod
    def _validate_manifest(manifest, members):
        if not isinstance(manifest, dict) or manifest.get('app_name') != APP_NAME:
            raise BackupValidationError('备份应用名称不匹配')
        for field, supported in (('format_version', BACKUP_FORMAT_VERSION), ('database_version', DB_SCHEMA_VERSION)):
            if type(manifest.get(field)) is not int or manifest[field] != supported:
                label = '备份格式版本' if field == 'format_version' else '数据库结构版本'
                raise BackupValidationError(f'不支持的{label}：{manifest.get(field)!r}；当前支持 {supported}，没有自动迁移路径')
        # app_version is provenance, never a compatibility gate.
        if not isinstance(manifest.get('app_version'), str) or not manifest['app_version'].strip():
            raise BackupValidationError('备份缺少应用版本')
        created = datetime.fromisoformat(manifest.get('created_at', ''))
        if created.tzinfo is None:
            raise BackupValidationError('备份时间必须包含时区')
        if manifest.get('database_file') != DATABASE_ENTRY or DATABASE_ENTRY not in members:
            raise BackupValidationError('备份缺少规定的 SQLite 文件')
        if manifest.get('includes_images') is not True:
            raise BackupValidationError('Backup V1 必须包含完整 Images 状态')
        if type(manifest.get('includes_settings')) is not bool:
            raise BackupValidationError('includes_settings 必须是布尔值')
        if manifest['includes_settings'] != (SETTINGS_ENTRY in members):
            raise BackupValidationError('备份 Settings 声明与文件不一致')

    def inspect_backup(self, archive_path):
        with tempfile.TemporaryDirectory(prefix='TenderSystem_validate_backup_') as directory:
            return self._extract_validated(archive_path, Path(directory))

    def restore_backup(self, archive_path, *, expected_digest=None):
        """Caller must prevent GUI operations and exit after a successful restore."""
        with runtime_maintenance(), tempfile.TemporaryDirectory(prefix='TenderSystem_restore_') as directory:
            extracted = Path(directory)
            info = self._extract_validated(archive_path, extracted, expected_digest)
            backups = self.data_root / 'Backups'
            backups.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safety = backups / f'{APP_NAME}_PreRestore_{timestamp}_{uuid.uuid4().hex[:8]}.zip'
            self.create_backup(safety)  # No current files have changed if this fails.
            # Stages live beside each target so every rename stays on one volume.
            workspaces = []
            changes = []
            try:
                pairs = [(self.database_path, extracted / DATABASE_ENTRY), (self.images, extracted / 'Images')]
                if info.manifest['includes_settings']:
                    pairs.append((self.settings, extracted / SETTINGS_ENTRY))
                for target, source in pairs:
                    if target.is_symlink():
                        raise RestoreError(f'恢复目标不能是链接：{target}')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    work = Path(tempfile.mkdtemp(prefix='.TenderSystem-restore-', dir=target.parent))
                    workspaces.append(work)
                    prepared = work / 'new'
                    if target == self.images:
                        if source.exists():
                            shutil.copytree(source, prepared)
                        else:
                            prepared.mkdir()
                    else:
                        shutil.copy2(source, prepared)
                    changes.append((target, prepared, work / 'old'))
                # Retire sidecars with the old database; never apply an old WAL
                # to the restored snapshot. The snapshot is in DELETE mode.
                for suffix in ('-wal', '-shm', '-journal'):
                    sidecar = Path(str(self.database_path) + suffix)
                    if sidecar.exists():
                        changes.insert(0, (sidecar, None, workspaces[0] / ('old' + suffix)))
                journal = []
                try:
                    for target, prepared, old in changes:
                        existed = target.exists()
                        journal.append([target, old, existed, False, False])
                        if existed:
                            os.replace(target, old)
                            journal[-1][3] = True
                        if prepared is not None:
                            os.replace(prepared, target)
                            journal[-1][4] = True
                    _validate_database(self.database_path)
                    if _validate_attachment_paths(self.database_path, self.data_root) != info.missing_images:
                        raise RestoreError('恢复后附件引用状态与已验证备份不一致')
                except BaseException as error:
                    rollback_errors = []
                    for target, old, existed, moved, installed in reversed(journal):
                        try:
                            if installed:
                                if target.is_dir():
                                    shutil.rmtree(target)
                                else:
                                    target.unlink(missing_ok=True)
                            if existed and moved:
                                os.replace(old, target)
                        except OSError as rollback_error:
                            rollback_errors.append(str(rollback_error))
                    if rollback_errors:
                        retained = ', '.join(str(path) for path in workspaces)
                        workspaces.clear()  # Preserve the old data for recovery.
                        raise RestoreRecoveryRequiredError(f'恢复失败且回退未完成；Safety Backup：{safety}；保留目录：{retained}；'
                                           + '; '.join(rollback_errors)) from error
                    raise RestoreError(f'恢复失败，原文件已回退；Safety Backup：{safety}；{error}') from error
            finally:
                for work in workspaces:
                    shutil.rmtree(work, ignore_errors=True)
            return RestoreResult(safety, info.manifest['includes_settings'])
