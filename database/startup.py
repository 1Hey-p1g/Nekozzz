"""Portable first launch reuses the existing no-overwrite V1 initializer."""
import sys
from pathlib import Path
from config.paths import DATA_ROOT
from database.initializer import create_empty_database
from database.runtime import runtime_connection, validate_runtime_path
from migration.migration_validator import validate_target_structure

def prepare_database(database_path=None, *, packaged=None, data_root=DATA_ROOT):
    packaged = getattr(sys, 'frozen', False) if packaged is None else packaged
    if database_path is None:
        if not packaged:
            raise ValueError('开发模式必须使用 --database 明确指定独立 V1 数据库')
        target = Path(data_root) / 'database' / 'TenderSystem-v1.db'
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            create_empty_database(target)
    else:
        target = Path(database_path)
    target = validate_runtime_path(target)
    with runtime_connection(target) as connection:
        validate_target_structure(connection)
    return target
