"""First launch and first migration always use isolated portable roots."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import closing
from database.startup import prepare_database
from database.initializer import create_empty_database
from database.runtime import runtime_connection
from migration.target_schema import TABLES
from services.data_management import DataManagementService
from gui.data_management import AccessMigrationDialog
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtCore import QCoreApplication, QEvent

class FirstLaunchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='TenderSystem_first_launch_')
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.db=self.root/'database/TenderSystem-v1.db'
        self.source=self.root/'source.accdb'
        self.source.write_bytes(b'Access original')

    def initialize(self):
        prepare_database(packaged=True,data_root=self.root)
        return DataManagementService(self.db,data_root=self.root)

    def fake_migration(self,source,target,**kwargs):
        self.assertEqual(Path(source),self.source)
        self.assertNotEqual(Path(target),self.db)
        self.assertFalse(Path(target).exists())
        create_empty_database(target)
        with runtime_connection(target,write=True) as connection:
            connection.execute('INSERT INTO 人员表(人员ID,姓名) VALUES(1,?)',('迁移人员',))
        return {'rows':1}

    def test_packaged_missing_creates_complete_empty_v1(self):
        with patch('database.startup.create_empty_database',wraps=create_empty_database) as initializer:
            self.initialize()
            initializer.assert_called_once_with(self.db)
        with runtime_connection(self.db) as connection:
            self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0],1)
            for table in TABLES:
                self.assertEqual(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0],0)
        before=self.db.read_bytes()
        with patch('database.startup.create_empty_database') as initializer:
            prepare_database(packaged=True,data_root=self.root)
            initializer.assert_not_called()
        self.assertEqual(before,self.db.read_bytes())

    def test_invalid_existing_never_rebuilt_and_dev_requires_explicit(self):
        self.db.parent.mkdir()
        self.db.write_bytes(b'invalid existing DB')
        with patch('database.startup.create_empty_database') as initializer:
            with self.assertRaises(sqlite3.DatabaseError):
                prepare_database(packaged=True,data_root=self.root)
            initializer.assert_not_called()
        self.assertEqual(self.db.read_bytes(),b'invalid existing DB')
        with self.assertRaises(ValueError):
            prepare_database(packaged=False,data_root=self.root)
        missing=self.root/'explicit-missing.db'
        with self.assertRaises(FileNotFoundError):
            prepare_database(missing,packaged=False,data_root=self.root)
        self.assertFalse(missing.exists())

    def test_success_replaces_only_default_empty_and_source_unchanged(self):
        service=self.initialize()
        self.assertTrue(service.can_migrate_as_current())
        original=self.source.read_bytes()
        with patch('services.data_management.migrate_access',side_effect=self.fake_migration):
            self.assertEqual(service.migrate_as_current(self.source),{'rows':1})
        self.assertFalse(service.can_migrate_as_current())
        with runtime_connection(self.db) as connection:
            self.assertEqual(connection.execute('SELECT 姓名 FROM 人员表').fetchone()[0],'迁移人员')
        self.assertEqual(original,self.source.read_bytes())
        self.assertFalse(list(self.db.parent.glob('.TenderSystem-first-migration-*')))

    def test_nonempty_or_nondefault_forbidden(self):
        service=self.initialize()
        with runtime_connection(self.db,write=True) as connection:
            connection.execute('INSERT INTO 财务报告表(年度ID,财务报告年度) VALUES(1,?)',('2026',))
        before=self.db.read_bytes()
        with patch('services.data_management.migrate_access') as migrate:
            with self.assertRaises(ValueError): service.migrate_as_current(self.source)
            migrate.assert_not_called()
        self.assertEqual(before,self.db.read_bytes())
        other=self.root/'other.db'; create_empty_database(other)
        self.assertFalse(DataManagementService(other,data_root=self.root).can_migrate_as_current())

    def test_engine_or_target_validation_failure_preserves_current(self):
        service=self.initialize(); before=self.db.read_bytes()
        for error in (RuntimeError('ODBC'),ValueError('mapping/validation')):
            with patch('services.data_management.migrate_access',side_effect=error):
                with self.assertRaises(type(error)): service.migrate_as_current(self.source)
            self.assertEqual(before,self.db.read_bytes())
        def invalid(source,target,**kwargs):
            Path(target).write_bytes(b'broken target'); return {'rows':1}
        with patch('services.data_management.migrate_access',side_effect=invalid):
            with self.assertRaises(sqlite3.DatabaseError): service.migrate_as_current(self.source)
        self.assertEqual(before,self.db.read_bytes())
        self.assertFalse(list(self.db.parent.glob('.TenderSystem-first-migration-*')))

    def test_change_during_migration_aborts_and_preserves_new_user_record(self):
        service=self.initialize()
        def changed(source,target,**kwargs):
            result=self.fake_migration(source,target,**kwargs)
            with runtime_connection(self.db,write=True) as connection:
                connection.execute('INSERT INTO 人员表(人员ID,姓名) VALUES(99,?)',('用户新录入',))
            return result
        with patch('services.data_management.migrate_access',side_effect=changed):
            with self.assertRaises(ValueError): service.migrate_as_current(self.source)
        with runtime_connection(self.db) as connection:
            self.assertEqual(connection.execute('SELECT 人员ID FROM 人员表').fetchone()[0],99)

    def test_replacement_failure_restores_original_empty_file(self):
        service=self.initialize(); before=self.db.read_bytes()
        from database.initializer import publish_staging
        calls=[]
        def fail_once(stage,target):
            calls.append(stage)
            if len(calls)==1: raise OSError('Injected publication error')
            return publish_staging(stage,target)
        with patch('services.data_management.migrate_access',side_effect=self.fake_migration), \
             patch('services.data_management.publish_staging',side_effect=fail_once):
            with self.assertRaises(OSError): service.migrate_as_current(self.source)
        self.assertEqual(before,self.db.read_bytes())
        self.assertTrue(service.can_migrate_as_current())

    def test_changed_empty_fingerprint_and_busy_reader_aborts(self):
        service=self.initialize()
        def touch(source,target,**kwargs):
            result=self.fake_migration(source,target,**kwargs)
            stat=self.db.stat(); os.utime(self.db,ns=(stat.st_atime_ns,stat.st_mtime_ns+1000000000))
            return result
        with patch('services.data_management.migrate_access',side_effect=touch):
            with self.assertRaises(ValueError): service.migrate_as_current(self.source)
        before=self.db.read_bytes()
        with closing(sqlite3.connect(self.db)) as reader:
            reader.execute('BEGIN'); reader.execute('SELECT * FROM 人员表').fetchall()
            with patch('services.data_management.migrate_access',side_effect=self.fake_migration):
                with self.assertRaises(sqlite3.OperationalError): service.migrate_as_current(self.source)
            reader.rollback()
        self.assertEqual(before,self.db.read_bytes())

    def test_dialog_default_current_cancel_and_success_exit(self):
        service=self.initialize(); window=QMainWindow()
        dialog=AccessMigrationDialog(window,service)
        def dispose():
            dialog.close()
            window.setEnabled(True)
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
            self.app.processEvents()
        self.addCleanup(dispose)
        self.assertTrue(dialog.use_current.isChecked())
        self.assertFalse(dialog.target.isEnabled())
        dialog.source.setText(str(self.source))
        with patch.object(QMessageBox,'question',return_value=QMessageBox.No), \
             patch.object(service,'migrate_as_current') as migrate:
            dialog.start(); migrate.assert_not_called()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes), \
             patch.object(QMessageBox,'information') as information, \
             patch.object(window,'close') as close, \
             patch('services.data_management.migrate_access',side_effect=self.fake_migration):
            dialog.start(); information.assert_called_once(); close.assert_called_once()
        self.assertTrue(window._restore_completed)

    def test_new_icon_and_spec(self):
        from config.paths import resource_path
        self.assertEqual(hashlib.sha256(resource_path('resources/icon.png').read_bytes()).hexdigest(),
                         '263cd398a16dfa9c2158b27a9d8e372a060e4a19319bd0719229f52c09fa6b2f')
        self.assertIn("root/'resources/icon.ico'",Path('Nekozzz.spec').read_text())
