"""Connections for the versioned, explicitly selected runtime database."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from config.paths import DATABASE_FILE
from version import DB_SCHEMA_VERSION


# Runtime repositories never retain connections. Maintenance excludes all their
# operations while complete data files are being replaced; no hot reload.
_runtime_lock = RLock()


@contextmanager
def runtime_maintenance():
    with _runtime_lock:
        yield


def validate_runtime_path(path):
    target = Path(path).expanduser().resolve()
    if target == DATABASE_FILE.resolve():
        raise ValueError("正式 database/tender.db 尚未切换到 V1；请选择独立 V1 数据库")
    if not target.is_file():
        raise FileNotFoundError(f"V1 数据库不存在: {target}")
    return target


@contextmanager
def runtime_connection(path, *, write=False):
    with _runtime_lock:
        with _open_runtime_connection(path, write=write) as connection:
            yield connection


@contextmanager
def _open_runtime_connection(path, *, write=False):
    target = validate_runtime_path(path)
    mode = "rw" if write else "ro"
    connection = sqlite3.connect(target.as_uri() + f"?mode={mode}", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise RuntimeError("SQLite 外键未启用")
        if connection.execute("PRAGMA user_version").fetchone()[0] != DB_SCHEMA_VERSION:
            raise ValueError(f"所选文件不是 V1 数据库: {target}")
        yield connection
        if write:
            connection.commit()
    except BaseException:
        if write:
            connection.rollback()
        raise
    finally:
        connection.close()
