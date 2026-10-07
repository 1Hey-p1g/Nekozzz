import contextlib
import hashlib
import io
import importlib.util
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from config.paths import ACCESS_FILE, DATABASE_FILE, EXCEL_FILE, PROJECT_ROOT, UI_FILE
from migration.migration_manager import migrate_database, _temporary_access_copy
from migration.access_connection import get_access_connection


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class MigrationPathTests(unittest.TestCase):
    def test_portable_paths_use_executable_directory(self):
        with tempfile.TemporaryDirectory(prefix="TenderSystem_portable_") as directory:
            executable = Path(directory) / "TenderSystem.exe"
            spec = importlib.util.spec_from_file_location("portable_path_test", PROJECT_ROOT / "config" / "paths.py")
            module = importlib.util.module_from_spec(spec)
            with mock.patch.object(sys, "frozen", True, create=True), mock.patch.object(sys, "executable", str(executable)):
                spec.loader.exec_module(module)
            self.assertEqual(Path(directory), module.DATA_ROOT)
            self.assertEqual(Path(directory) / "database" / "tender.db", module.DATABASE_FILE)
            self.assertEqual(Path(directory) / "Images", module.IMAGES_DIR)
            self.assertEqual(Path(directory) / "Images" / "example.png", module.resolve_image_path("Images/example.png"))

    def test_odbc_can_only_open_project_outside_copy(self):
        with self.assertRaises(ValueError):
            get_access_connection(ACCESS_FILE)
        with _temporary_access_copy(ACCESS_FILE) as copy:
            self.assertNotIn(PROJECT_ROOT, copy.parents)
            self.assertEqual(file_digest(ACCESS_FILE), file_digest(copy))

    def test_paths_do_not_depend_on_working_directory(self):
        original = Path.cwd()
        with tempfile.TemporaryDirectory(prefix="TenderSystem_paths_") as directory:
            try:
                os.chdir(directory)
                self.assertEqual(PROJECT_ROOT, Path(__file__).resolve().parents[1])
                for resource in (ACCESS_FILE, EXCEL_FILE, UI_FILE):
                    self.assertTrue(resource.is_file())
            finally:
                os.chdir(original)

    def test_migration_uses_only_new_external_target(self):
        original_hashes = {path: file_digest(path) for path in (ACCESS_FILE, EXCEL_FILE, DATABASE_FILE)}
        with tempfile.TemporaryDirectory(prefix="TenderSystem_migration_") as directory:
            temporary = Path(directory)
            access_copy = temporary / ACCESS_FILE.name
            shutil.copy2(ACCESS_FILE, access_copy)
            target = temporary / "new.db"

            with self.assertRaises(FileNotFoundError):
                migrate_database(target, EXCEL_FILE, temporary / "missing.accdb")
            with self.assertRaises(FileNotFoundError):
                migrate_database(target, temporary / "missing.xlsx", access_copy)
            with self.assertRaises(ValueError):
                migrate_database(DATABASE_FILE, EXCEL_FILE, access_copy)
            with self.assertRaises(ValueError):
                migrate_database(ACCESS_FILE.parent / "new.db", EXCEL_FILE, access_copy)
            existing = temporary / "existing.db"
            existing.touch()
            with self.assertRaises(FileExistsError):
                migrate_database(existing, EXCEL_FILE, access_copy)

            with contextlib.redirect_stdout(io.StringIO()) as output:
                migrate_database(target, EXCEL_FILE, access_copy)
            self.assertIn("数据验证通过", output.getvalue())

            connection = sqlite3.connect(target.as_uri() + "?mode=ro&immutable=1", uri=True)
            try:
                tables = [row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )]
                self.assertEqual(13, len(tables))
                self.assertEqual(1502, sum(connection.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0] for table in tables))
            finally:
                connection.close()

        self.assertEqual(original_hashes, {
            path: file_digest(path) for path in (ACCESS_FILE, EXCEL_FILE, DATABASE_FILE)
        })


if __name__ == "__main__":
    unittest.main()
