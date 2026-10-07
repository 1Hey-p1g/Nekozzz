"""Safe one-shot migration from a caller-supplied Access database."""

import hashlib
import shutil
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from config.paths import EXCEL_FILE
from database.initializer import check_new_target, new_staging_path, publish_staging
from migration.access_connection import get_access_connection
from migration.access_reader import get_table_rows
from migration.migration_order import get_insert_order
from migration.migration_validator import validate_target_database
from migration.schema_loader import load_database_schema
from migration.sqlite_schema import create_target_schema
from migration.sqlite_writer import insert_mapped_rows
from migration.target_schema import TABLES, FOREIGN_KEYS, mapping_for
from version import DB_SCHEMA_VERSION


def _check_access_columns(connection, source_schema):
    """Check the actual ACCDB columns, not just the workbook's field list."""
    actual_tables = {row.table_name for row in connection.cursor().tables(tableType="TABLE")}
    expected_tables = set(source_schema["tables"])
    if actual_tables != expected_tables:
        raise ValueError(
            f"ACCDB 业务表与 Excel 不一致；缺少={sorted(expected_tables - actual_tables)}，"
            f"新增={sorted(actual_tables - expected_tables)}"
        )
    access_types = {
        "Currency": {("CURRENCY", 2)},
        "Date/Time": {("DATETIME", 93)},
        "Long Integer": {("COUNTER", 4), ("INTEGER", 4)},
        "Memo / Long Text": {("LONGCHAR", -10)},
        "Text": {("VARCHAR", -9)},
        "Yes/No": {("BIT", -7)},
    }
    for table, info in source_schema["tables"].items():
        actual_rows = list(connection.cursor().columns(table=table))
        actual = {row.column_name: row for row in actual_rows}
        expected = info["fields"]
        expected_names = {field["name"] for field in expected}
        if len(actual) != len(actual_rows) or set(actual) != expected_names:
            raise ValueError(
                f"{table}: ACCDB 字段与 Excel 不一致；缺少={sorted(expected_names - set(actual))}，"
                f"新增={sorted(set(actual) - expected_names)}"
            )
        for field in expected:
            row = actual[field["name"]]
            if (row.type_name, row.data_type) not in access_types.get(field["data_type"], set()):
                raise ValueError(
                    f"{table}.{field['name']}: ACCDB 类型 {row.type_name}/{row.data_type} "
                    f"与 Excel {field['data_type']} 不一致"
                )


@contextmanager
def _temporary_access_copy(source_path):
    """Keep ODBC and its lock file away from the caller's original source."""
    with TemporaryDirectory(prefix="TenderSystem_access_") as directory:
        copy = Path(directory) / "source.accdb"
        with source_path.open("rb") as stream:
            before = hashlib.file_digest(stream, "sha256").digest()
        shutil.copy2(source_path, copy)
        with source_path.open("rb") as stream:
            after = hashlib.file_digest(stream, "sha256").digest()
        with copy.open("rb") as stream:
            copied = hashlib.file_digest(stream, "sha256").digest()
        if not (before == after == copied):
            raise RuntimeError("Access 源文件在复制期间发生变化；未开始迁移")
        yield copy


def migrate_access(source_path, target_path, excel_file=EXCEL_FILE):
    """Validate source structure, migrate and publish a new V1 SQLite database.

    The source may have any name and row count. ODBC only opens a system-temp
    copy, so the supplied original cannot acquire a migration lock file.
    """
    target = check_new_target(target_path)
    excel = Path(excel_file).resolve()
    if source_path is None:
        raise ValueError("必须显式指定 Access 源文件")
    access = Path(source_path).resolve()
    if not excel.is_file():
        raise FileNotFoundError(f"Excel 结构文件不存在：{excel}")
    if not access.is_file():
        raise FileNotFoundError(f"Access 文件不存在：{access}")

    source_schema = load_database_schema(excel)
    mapping = mapping_for(source_schema)
    # Reuse the existing topological sort with the approved target dependencies.
    target_order = get_insert_order({
        "tables": {name: {} for name in TABLES},
        "relationships": [
            {"child_table": child, "parent_table": parent}
            for child, _, parent, _ in FOREIGN_KEYS
        ],
    })

    with _temporary_access_copy(access) as access_copy, closing(get_access_connection(access_copy)) as source:
        _check_access_columns(source, source_schema)
        stage = new_staging_path(target)
        connection = None
        try:
            connection = sqlite3.connect(stage)
            connection.execute("PRAGMA foreign_keys=ON")
            if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                raise RuntimeError("无法启用 SQLite 外键")
            connection.execute("BEGIN")
            create_target_schema(connection)
            connection.execute(f"PRAGMA user_version={DB_SCHEMA_VERSION}")
            for table in target_order:
                source_fields = [field["name"] for field in source_schema["tables"][table]["fields"]]
                rows = get_table_rows(source, table, source_fields)
                insert_mapped_rows(connection, table, rows, mapping[table])
            result = validate_target_database(source, connection, source_schema, mapping)
            connection.commit()
            connection.close()
            connection = None
            publish_staging(stage, target)
            print(f"数据验证通过：{result}")
            return result
        except Exception:
            if connection is not None:
                connection.rollback()
                connection.close()
            stage.unlink(missing_ok=True)
            raise


def migrate_database(sqlite_file, excel_file=EXCEL_FILE, access_file=None):
    """Compatibility wrapper for existing target-first callers."""
    return migrate_access(access_file, sqlite_file, excel_file)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="将 Access 源文件迁移到全新 SQLite 文件")
    parser.add_argument("--access-source", "--access-copy", dest="access_source", required=True, type=Path)
    parser.add_argument("--sqlite-target", required=True, type=Path)
    parser.add_argument("--excel", default=EXCEL_FILE, type=Path)
    arguments = parser.parse_args()
    migrate_access(arguments.access_source, arguments.sqlite_target, arguments.excel)
