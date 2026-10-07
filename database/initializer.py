"""V1 database creation and no-overwrite publication for Windows Portable data."""

import os
import sqlite3
import tempfile
from pathlib import Path

from config.paths import ACCESS_FILE, DATABASE_FILE
from migration.migration_validator import validate_target_structure
from migration.sqlite_schema import create_target_schema
from version import DB_SCHEMA_VERSION


def check_new_target(target_path):
    if target_path is None:
        raise ValueError("必须显式指定新 SQLite 数据库路径")
    target = Path(target_path).resolve()
    if target == DATABASE_FILE.resolve():
        raise ValueError("禁止创建或覆盖现有正式 tender.db")
    if ACCESS_FILE.parent.resolve() in target.parents:
        raise ValueError("禁止在 access source 中创建 SQLite 数据库")
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"目标数据库已存在：{target}")
    if not target.parent.is_dir():
        raise FileNotFoundError(f"目标目录不存在：{target.parent}")
    return target


def new_staging_path(target):
    """Stage beside the final target so publication stays on one filesystem."""
    descriptor, path = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".sqlite-tmp", dir=target.parent
    )
    os.close(descriptor)
    return Path(path)


def publish_staging(stage, target):
    """Publish an already closed, verified database without replacing a target."""
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"目标数据库在验证期间出现：{target}")
    if os.name == "nt":
        # Windows rename is atomic on the same volume and refuses an existing
        # destination, including a race after the check above.
        os.rename(stage, target)
        return
    os.link(stage, target)  # On other platforms, never use overwrite-capable rename.
    try:
        stage.unlink()
    except OSError:
        pass  # The verified target is published; leftover staging is harmless.


def create_empty_database(target_path):
    """Create, check and publish a zero-row V1 SQLite database at a new path."""
    target = check_new_target(target_path)
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
        result = validate_target_structure(connection, require_empty=True)
        connection.commit()
        connection.close()
        connection = None
        publish_staging(stage, target)
        return result
    except Exception:
        if connection is not None:
            connection.rollback()
            connection.close()
        stage.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="创建全新的空白 V1 SQLite 数据库")
    parser.add_argument("--sqlite-target", required=True, type=Path)
    arguments = parser.parse_args()
    print(create_empty_database(arguments.sqlite_target))
