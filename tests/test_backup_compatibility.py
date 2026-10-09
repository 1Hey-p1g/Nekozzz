"""Backup compatibility tests; frozen 0.9.2 writer and test-owned data only."""
import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from services.backup import BackupValidationError, DATABASE_ENTRY
from database.runtime import runtime_connection
from tests import test_data_management as fixture


class BackupCompatibilityTests(TestCase):
    setUp = fixture.DataManagementTests.setUp
    state = fixture.DataManagementTests.state
    create = fixture.DataManagementTests.create
    rewrite = fixture.DataManagementTests.rewrite
    change_live_data = fixture.DataManagementTests.change_live_data

    def test_frozen_092_writer_restores_on_different_app_version(self):
        source = Path(__file__).resolve().parents[1] / 'release/Nekozzz-0.9.2/source/services/backup.py'
        spec = importlib.util.spec_from_file_location('frozen_092_backup_test', source)
        frozen = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = frozen
        self.addCleanup(sys.modules.pop, spec.name, None)
        version_spec = importlib.util.spec_from_file_location('frozen_092_version', source.parents[1] / 'version.py')
        frozen_version = importlib.util.module_from_spec(version_spec)
        version_spec.loader.exec_module(frozen_version)
        # Execute the actual historical writer with its own immutable version input.
        with patch.dict(sys.modules, {'version': frozen_version}):
            spec.loader.exec_module(frozen)
        self.assertEqual('0.9.2', frozen.APP_VERSION)
        archive = frozen.BackupService(self.db, data_root=self.root).create_backup(self.root / '092.zip')
        original_zip = archive.read_bytes()
        original = self.state()
        self.change_live_data()
        with patch('services.backup.APP_VERSION', '0.9.3'):
            info = self.backups.inspect_backup(archive)
            self.assertEqual('0.9.2', info.manifest['app_version'])
            result = self.backups.restore_backup(archive, expected_digest=info.sha256)
            self.assertEqual('0.9.3', self.backups.inspect_backup(result.safety_backup).manifest['app_version'])
        self.assertEqual(original[1:], self.state()[1:])
        with zipfile.ZipFile(archive) as saved:
            self.assertEqual(saved.read(DATABASE_ENTRY), self.db.read_bytes())
        self.assertEqual(original_zip, archive.read_bytes())

    def test_arbitrary_source_app_version_is_not_a_gate(self):
        original = self.state()
        archive = self.rewrite(self.create(), manifest_changes={'app_version': 'older-release'})
        self.change_live_data()
        self.backups.restore_backup(archive)
        self.assertEqual(original[1:], self.state()[1:])

    def test_unknown_old_new_missing_versions_rejected_without_mutation(self):
        source = self.create()
        before = self.state()
        for field in ('format_version', 'database_version'):
            for value in (None, 0, 2, True, '1'):
                with self.subTest(field=field, value=value):
                    archive = self.rewrite(source, manifest_changes={field: value})
                    with self.assertRaisesRegex(BackupValidationError, '版本'):
                        self.backups.restore_backup(archive)
                    self.assertEqual(before, self.state())
        self.assertFalse((self.root / 'Backups').exists())

    def test_removed_or_malformed_inventory_never_bypasses_hashes(self):
        source = self.create()
        before = self.state()
        for value in (None, {}, [], {'Images/legacy.jpg': 'fake'}):
            with self.subTest(value=value), self.assertRaisesRegex(BackupValidationError, '清单'):
                self.backups.restore_backup(self.rewrite(source, manifest_changes={'files': value}))
            self.assertEqual(before, self.state())

    def test_resource_ceilings_reject_before_restoring(self):
        source = self.create()
        before = self.state()
        for name, value in (('MAX_ARCHIVE_ENTRIES', 1), ('MAX_MEMBER_BYTES', 1),
                            ('MAX_EXTRACTED_BYTES', 1)):
            with self.subTest(name=name), patch('services.backup.' + name, value):
                with self.assertRaisesRegex(BackupValidationError, '安全上限'):
                    self.backups.restore_backup(source)
            self.assertEqual(before, self.state())

    def test_corrupt_sqlite_with_matching_inventory_rejected(self):
        source = self.create()
        with zipfile.ZipFile(source) as archive:
            payload = {i.filename: archive.read(i) for i in archive.infolist()}
        import hashlib
        payload[DATABASE_ENTRY] = b'not sqlite'
        manifest = json.loads(payload['backup.json'])
        manifest['files'][DATABASE_ENTRY] = hashlib.sha256(payload[DATABASE_ENTRY]).hexdigest()
        payload['backup.json'] = json.dumps(manifest).encode()
        target = self.root / 'corrupt.zip'
        with zipfile.ZipFile(target, 'w') as archive:
            for name, data in payload.items():
                archive.writestr(name, data)
        before = self.state()
        with self.assertRaises(BackupValidationError):
            self.backups.restore_backup(target)
        self.assertEqual(before, self.state())

    def test_attachment_reference_restore_and_missing_reference_warning(self):
        with runtime_connection(self.db, write=True) as connection:
            connection.execute("INSERT INTO 人员证书图表(ID,证书ID,路径) VALUES(1,9,'Images/legacy.jpg')")
        source = self.create()
        self.assertEqual((), self.backups.inspect_backup(source).missing_images)
        self.change_live_data()
        self.backups.restore_backup(source)
        with runtime_connection(self.db) as connection:
            self.assertEqual('Images/legacy.jpg', connection.execute('SELECT 路径 FROM 人员证书图表').fetchone()[0])
        self.assertEqual(b'legacy image', (self.images / 'legacy.jpg').read_bytes())
        (self.images / 'legacy.jpg').unlink()
        missing = self.create('missing.zip')
        self.assertEqual(('Images/legacy.jpg',), self.backups.inspect_backup(missing).missing_images)

    def test_database_attachment_traversal_rejected(self):
        with runtime_connection(self.db, write=True) as connection:
            connection.execute("INSERT INTO 人员证书图表(ID,证书ID,路径) VALUES(1,9,'Images/../../outside.jpg')")
        before = self.state()
        with self.assertRaisesRegex(BackupValidationError, '路径不安全'):
            self.create()
        self.assertEqual(before, self.state())
