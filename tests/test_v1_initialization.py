"""Independent blank V1 creation and no-overwrite publication tests."""

import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from config.paths import DATABASE_FILE
from database.initializer import create_empty_database
from migration.target_schema import TABLES


class EmptyDatabaseTests(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="TenderSystem_blank_")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def test_blank_v1_has_all_schema_and_zero_rows(self):
        target = self.directory / "blank.db"
        result = create_empty_database(target)
        self.assertEqual({"tables": 13, "fields": 82, "foreign_keys": 10}, result)
        with closing(sqlite3.connect(target)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            self.assertEqual(1, connection.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual([], list(connection.execute("PRAGMA foreign_key_check")))
            for table in TABLES:
                self.assertEqual(0, connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        self.assertEqual([], list(self.directory.glob(".blank.db.*.sqlite-tmp")))

    def test_existing_and_protected_target_rejected(self):
        target = self.directory / "existing.db"
        target.write_bytes(b"sentinel")
        with self.assertRaises(FileExistsError):
            create_empty_database(target)
        self.assertEqual(b"sentinel", target.read_bytes())
        with self.assertRaises(ValueError):
            create_empty_database(DATABASE_FILE)

    def test_validation_failure_leaves_no_database(self):
        target = self.directory / "failed.db"
        with mock.patch("database.initializer.validate_target_structure", side_effect=ValueError("故意结构失败")):
            with self.assertRaisesRegex(ValueError, "故意结构失败"):
                create_empty_database(target)
        self.assertFalse(target.exists())
        self.assertEqual([], list(self.directory.glob(".failed.db.*.sqlite-tmp")))

    def test_target_appearing_before_publish_is_preserved(self):
        target = self.directory / "raced.db"
        def competing_validation(connection, require_empty=False):
            target.write_bytes(b"another-process")
            return {"tables": 13, "fields": 82, "foreign_keys": 10}
        with mock.patch("database.initializer.validate_target_structure", side_effect=competing_validation):
            with self.assertRaises(FileExistsError):
                create_empty_database(target)
        self.assertEqual(b"another-process", target.read_bytes())
        self.assertEqual([], list(self.directory.glob(".raced.db.*.sqlite-tmp")))
