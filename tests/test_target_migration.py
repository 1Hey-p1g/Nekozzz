"""Isolation and integrity tests for the approved 85-to-82 migration."""

from decimal import Decimal
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
from copy import deepcopy
import shutil
import sqlite3

from config.paths import ACCESS_FILE, DATABASE_FILE, EXCEL_FILE, PROJECT_ROOT, IMAGES_DIR, resolve_image_path
from migration.access_connection import get_access_connection
from migration.migration_manager import migrate_access, migrate_database
from migration.migration_validator import validate_image_pages
from migration.sqlite_schema import create_target_schema
from migration.sqlite_writer import convert_value
from migration.target_schema import TABLES, mapping_for
from migration.schema_loader import load_database_schema


class TargetMigrationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = TemporaryDirectory(prefix="TenderSystem_target_")
        cls.directory = Path(cls.temporary.name)
        cls.access = cls.directory / "Database2.accdb"
        cls.target = cls.directory / "migrated.db"
        shutil.copy2(ACCESS_FILE, cls.access)
        cls.result = migrate_access(cls.access, cls.target)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def connect(self):
        connection = sqlite3.connect(self.target)
        connection.execute("PRAGMA foreign_keys=ON")
        self.addCleanup(connection.close)
        self.addCleanup(connection.rollback)
        return connection

    def test_structure_counts_and_excluded_fields(self):
        self.assertEqual({"tables": 13, "fields": 82, "rows": 1502, "foreign_keys": 10}, self.result)
        source = load_database_schema(EXCEL_FILE)
        mapping = mapping_for(source)
        self.assertEqual(85, sum(map(len, mapping.values())))
        self.assertEqual(82, sum(bool(target) for rows in mapping.values() for _, target, _ in rows))
        con = self.connect()
        for table, (primary, fields) in TABLES.items():
            actual = list(con.execute(f'PRAGMA table_info("{table}")'))
            self.assertEqual([name for name, _ in fields], [row[1] for row in actual])
            self.assertEqual([primary], [row[1] for row in actual if row[5]])
        self.assertEqual([], list(con.execute("PRAGMA foreign_key_check")))
        self.assertEqual(1, con.execute("PRAGMA user_version").fetchone()[0])
        self.assertNotIn("项目负责人", [row[1] for row in con.execute('PRAGMA table_info("公司业绩表")')])
        self.assertEqual(131, con.execute('SELECT COUNT(*) FROM 人员表').fetchone()[0])
        for table in ("公司资质表", "人员证书表"):
            self.assertNotIn("是否选择", [row[1] for row in con.execute(f'PRAGMA table_info("{table}")')])
        self.assertEqual(818, sum(con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                                  for t in ("公司资质图表", "人员证书图表", "财务报告图表", "公司业绩图表", "获奖工程图表")))

    def test_mapping_rejects_unmapped_and_changed_source_types(self):
        source = load_database_schema(EXCEL_FILE)
        changed = deepcopy(source)
        changed["tables"]["人员表"]["fields"].append({"name": "意外字段", "data_type": "Text"})
        with self.assertRaises(ValueError):
            mapping_for(changed)
        changed = deepcopy(source)
        selection = next(field for field in changed["tables"]["人员证书表"]["fields"] if field["name"] == "是否选择")
        selection["data_type"] = "Text"
        with self.assertRaises(ValueError):
            mapping_for(changed)

    def test_leader_cases_and_currency(self):
        con = self.connect()
        leaders = dict(con.execute('SELECT 业绩ID, 人员ID FROM 人员业绩表 WHERE 担任角色=?', ("项目负责人",)))
        for project in (11, 17):
            self.assertNotIn(project, leaders)
        for project in (26, 27):
            self.assertIn(project, leaders)
        with get_access_connection(self.access) as access:
            source = dict(access.cursor().execute("SELECT [业绩ID], [合同金额] FROM [公司业绩表]").fetchall())
        for project, amount in con.execute('SELECT 业绩ID, 合同金额_scaled FROM 公司业绩表'):
            self.assertEqual(source[project], None if amount is None else Decimal(amount) / Decimal(10000))

    def test_primary_foreign_unique_and_restrict(self):
        con = self.connect()
        existing = con.execute('SELECT ID,人员ID,业绩ID,担任角色 FROM 人员业绩表 LIMIT 1').fetchone()
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute('INSERT INTO 人员业绩表 VALUES (?,?,?,?)', (existing[0], existing[1], existing[2], "技术负责人"))
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute('INSERT INTO 人员业绩表 VALUES (?,?,?,?)', (99990, *existing[1:]))
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute('INSERT INTO 人员业绩表 VALUES (?,?,?,?)', (99991, 999999, existing[2], "技术负责人"))
        another_person = con.execute('SELECT 人员ID FROM 人员表 WHERE 人员ID<>? LIMIT 1', (existing[1],)).fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute('INSERT INTO 人员业绩表 VALUES (?,?,?,?)', (99992, another_person, existing[2], "项目负责人"))
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute('INSERT INTO 人员业绩表 VALUES (?,?,?,?)', (99993, another_person, existing[2], "   "))
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute('INSERT INTO 人员业绩表 VALUES (?,?,?,?)', (99996, another_person, existing[2], "\u3000\t"))
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute('INSERT INTO 人员业绩表 VALUES (?,?,?,?)', (99995, another_person, existing[2], None))
        con.execute('INSERT INTO 人员业绩表 VALUES (?,?,?,?)', (99994, existing[1], existing[2], "技术负责人"))
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute('DELETE FROM 公司业绩表 WHERE 业绩ID=?', (existing[2],))

    def test_page_constraints_and_numeric_order(self):
        con = self.connect()
        validate_image_pages(con)
        group = con.execute('SELECT 资质ID FROM 公司资质图表 GROUP BY 资质ID HAVING COUNT(*)>1 LIMIT 1').fetchone()[0]
        notes = [int(row[0]) for row in con.execute(
            'SELECT 备注 FROM 公司资质图表 WHERE 资质ID=? ORDER BY CAST(备注 AS INTEGER),ID', (group,))]
        self.assertEqual(list(range(1, len(notes)+1)), notes)
        row_id = con.execute('SELECT ID FROM 公司资质图表 WHERE 资质ID=? LIMIT 1', (group,)).fetchone()[0]
        other_note = con.execute('SELECT 备注 FROM 公司资质图表 WHERE 资质ID=? AND ID<>? LIMIT 1', (group, row_id)).fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute('UPDATE 公司资质图表 SET 备注=? WHERE ID=?', (other_note, row_id))
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute('UPDATE 公司资质图表 SET 备注=? WHERE ID=?', ("nonnumeric", row_id))
        con.execute('UPDATE 公司资质图表 SET 备注=? WHERE ID=?', ("99", row_id))
        with self.assertRaises(ValueError):
            validate_image_pages(con)

    def test_text_pages_1_through_10_sort_numerically(self):
        con = sqlite3.connect(":memory:")
        self.addCleanup(con.close)
        con.execute("PRAGMA foreign_keys=ON")
        create_target_schema(con)
        con.execute('INSERT INTO 公司信息表 (公司ID,公司名称) VALUES (1,?)', ("测试公司",))
        con.execute('INSERT INTO 公司资质表 (资质ID,公司ID,资质证书名称) VALUES (1,1,?)', ("测试资质",))
        con.executemany(
            'INSERT INTO 公司资质图表 (ID,资质ID,路径,备注) VALUES (?,1,?,?)',
            ((page, f"Images/{page}.png", str(page)) for page in range(10, 0, -1)),
        )
        validate_image_pages(con)
        ordered = [row[0] for row in con.execute(
            'SELECT 备注 FROM 公司资质图表 WHERE 资质ID=1 ORDER BY CAST(备注 AS INTEGER),ID'
        )]
        self.assertEqual([str(i) for i in range(1, 11)], ordered)

    def test_conversion_rejects_non_midnight_and_float(self):
        with self.assertRaisesRegex(ValueError, "非午夜"):
            convert_value(datetime(2020, 1, 2, 1), "D", "人员表", 1, "进入系统日期")
        with self.assertRaisesRegex(ValueError, "Decimal"):
            convert_value(1.1, "M", "公司业绩表", 1, "合同金额_scaled")
        with self.assertRaisesRegex(ValueError, "64 位"):
            convert_value(Decimal("999999999999999999"), "M", "公司业绩表", 1, "合同金额_scaled")
        self.assertIsNone(convert_value(None, "T", "x", 1, "y"))
        self.assertEqual("", convert_value("", "T", "x", 1, "y"))
        self.assertEqual(0, convert_value(0, "P", "x", 1, "y"))

    def test_existing_target_and_failed_validation_never_publish(self):
        with self.assertRaises(FileExistsError):
            migrate_database(self.target, EXCEL_FILE, self.access)
        with self.assertRaises(ValueError):
            migrate_database(DATABASE_FILE, EXCEL_FILE, self.access)
        failed = self.directory / "failed.db"
        with mock.patch("migration.migration_manager.validate_target_database", side_effect=ValueError("故意校验失败")):
            with self.assertRaisesRegex(ValueError, "故意校验失败"):
                migrate_database(failed, EXCEL_FILE, self.access)
        self.assertFalse(failed.exists())
        self.assertEqual([], list(self.directory.glob(".failed.db.*.sqlite-tmp")))

    def test_mid_migration_failure_never_publishes(self):
        failed = self.directory / "midway.db"
        with mock.patch("migration.migration_manager.insert_mapped_rows", side_effect=ValueError("故意中途失败")):
            with self.assertRaisesRegex(ValueError, "故意中途失败"):
                migrate_access(self.access, failed)
        self.assertFalse(failed.exists())
        self.assertEqual([], list(self.directory.glob(".midway.db.*.sqlite-tmp")))

    def test_legacy_paths_preserved_and_safely_resolved(self):
        con = self.connect()
        image_path = con.execute('SELECT 路径 FROM 公司资质图表 LIMIT 1').fetchone()[0]
        self.assertEqual((PROJECT_ROOT / image_path).resolve(), resolve_image_path(image_path))
        self.assertEqual(PROJECT_ROOT / "Images", IMAGES_DIR)
        with self.assertRaises(ValueError):
            resolve_image_path("Images/../database/tender.db")
        with self.assertRaises(ValueError):
            resolve_image_path("image/new.png")
