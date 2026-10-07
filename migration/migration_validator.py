"""Pre-commit checks for the approved Access-to-SQLite migration."""

from collections import defaultdict

from config.paths import resolve_image_path
from migration.access_reader import get_table_rows
from migration.sqlite_writer import convert_value
from migration.target_schema import FOREIGN_KEYS, IMAGE_GROUPS, TABLES
from version import DB_SCHEMA_VERSION


def validate_image_pages(connection):
    """Validate numeric, unique, consecutive page numbers within every group."""
    for table, group_columns in IMAGE_GROUPS.items():
        columns = (*group_columns, "ID", "备注")
        sql = f'SELECT {", ".join(chr(34) + c + chr(34) for c in columns)} FROM "{table}"'
        groups = defaultdict(list)
        for row in connection.execute(sql):
            group = tuple(row[:len(group_columns)])
            image_id, note = row[-2:]
            if note is None:
                page = None
            elif isinstance(note, int) and dict(TABLES[table][1])["备注"] == "P":
                page = note
            elif isinstance(note, str) and note.isascii() and note.isdecimal():
                page = int(note)
            else:
                raise ValueError(f"{table}[{image_id}].备注: 非法页序 {note!r}")
            groups[group].append(page)
        for group, pages in groups.items():
            if len(pages) == 1 and pages[0] in (None, 0):
                continue
            if sorted(pages, key=lambda x: -1 if x is None else x) != list(range(1, len(pages) + 1)):
                raise ValueError(f"{table} 组 {group}: 页序必须连续为 1..{len(pages)}，实际 {pages}")


def validate_leader_text(access_connection):
    """Audit the old name without creating or overwriting person-project links."""
    projects = get_table_rows(access_connection, "公司业绩表", ["业绩ID", "项目负责人"])
    people = dict(get_table_rows(access_connection, "人员表", ["人员ID", "姓名"]))
    links = get_table_rows(access_connection, "人员业绩表", ["人员ID", "业绩ID", "担任角色"])
    leaders = {}
    for person_id, project_id, role in links:
        if role == "项目负责人":
            leaders.setdefault(project_id, []).append(people.get(person_id))
    issues = []
    for project_id, raw_name in projects:
        if raw_name is None or raw_name == "":
            continue  # Blank old label with or without a link is allowed.
        linked = leaders.get(project_id, [])
        if len(linked) != 1 or raw_name.strip() != linked[0]:
            issues.append(f"公司业绩表[{project_id}].项目负责人={raw_name!r}, 关联={linked!r}")
    if issues:
        raise ValueError("旧负责人文本与人员业绩关联不一致：" + "; ".join(issues))


def validate_target_structure(connection, require_empty=False):
    """Validate the V1 schema independently of any Access source."""
    actual_tables = {
        row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    if actual_tables != set(TABLES):
        raise ValueError(f"目标表清单错误: {actual_tables ^ set(TABLES)}")
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise ValueError("SQLite 外键约束未启用")
    if connection.execute("PRAGMA user_version").fetchone()[0] != DB_SCHEMA_VERSION:
        raise ValueError(f"SQLite user_version 必须为 {DB_SCHEMA_VERSION}")

    for table, (pk, fields) in TABLES.items():
        info = list(connection.execute(f'PRAGMA table_info("{table}")'))
        if [row[1] for row in info] != [name for name, _ in fields]:
            raise ValueError(f"{table}: 目标字段清单与定义不一致")
        if [row[1] for row in info if row[5]] != [pk]:
            raise ValueError(f"{table}: 主键不正确")
        for row, (name, kind) in zip(info, fields):
            expected_type = "INTEGER" if kind.rstrip("!") in ("I", "M", "P") else "TEXT"
            if row[2] != expected_type or (name != pk and bool(row[3]) != kind.endswith("!")) or row[4] is not None:
                raise ValueError(f"{table}.{name}: 类型、可空性或默认值不符合定义")
        create_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()[0]
        if "AUTOINCREMENT" in create_sql.upper():
            raise ValueError(f"{table}: 不允许 AUTOINCREMENT")
        if require_empty and connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] != 0:
            raise ValueError(f"{table}: 空白库不得有业务记录")

    actual_fk = set()
    for table in TABLES:
        for row in connection.execute(f'PRAGMA foreign_key_list("{table}")'):
            if row[5] != "RESTRICT" or row[6] != "RESTRICT":
                raise ValueError(f"{table}: 外键更新或删除规则不是 RESTRICT")
            actual_fk.add((table, row[3], row[2], row[4]))
    if actual_fk != set(FOREIGN_KEYS):
        raise ValueError(f"目标外键集合错误: {actual_fk ^ set(FOREIGN_KEYS)}")
    index_sql = dict(connection.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
    ))
    leader_sql = index_sql.get("ux_人员业绩_单项目负责人", "")
    if "WHERE \"担任角色\" = '项目负责人'" not in leader_sql:
        raise ValueError("缺少项目负责人部分唯一索引")
    indexes = list(connection.execute('PRAGMA index_list("人员业绩表")'))
    unique_columns = {
        tuple(row[2] for row in connection.execute(f'PRAGMA index_info("{index[1]}")'))
        for index in indexes if index[2]
    }
    if ("人员ID", "业绩ID", "担任角色") not in unique_columns:
        raise ValueError("缺少人员-工程-角色联合唯一约束")
    if not any(index[1] == "ux_人员业绩_单项目负责人" and index[2] and index[4]
               for index in indexes):
        raise ValueError("项目负责人索引不是部分唯一索引")
    for table in IMAGE_GROUPS:
        if not any(index[1] == f"ux_{table}_页序" and index[2]
                   for index in connection.execute(f'PRAGMA index_list("{table}")')):
            raise ValueError(f"{table}: 缺少正数页序唯一索引")
    errors = list(connection.execute("PRAGMA foreign_key_check"))
    if errors:
        raise ValueError(f"外键完整性异常: {errors[:5]}")
    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise ValueError("SQLite quick_check 未通过")
    return {"tables": len(TABLES), "fields": sum(len(fields) for _, fields in TABLES.values()), "foreign_keys": len(actual_fk)}


def validate_target_database(access_connection, sqlite_connection, source_schema, mapping):
    """Check schema, all mapped values, IDs, FKs, pages and leader audit before commit."""
    structure = validate_target_structure(sqlite_connection)
    total = 0
    for table, (_, fields) in TABLES.items():
        target_names = [name for name, _ in fields]
        source_names = [field["name"] for field in source_schema["tables"][table]["fields"]]
        source_rows = get_table_rows(access_connection, table, source_names)
        selected = [(i, target, kind) for i, (_, target, kind) in enumerate(mapping[table]) if target]
        sql = f'SELECT {", ".join(chr(34) + name + chr(34) for name in target_names)} FROM "{table}"'
        actual = {row[0]: tuple(row) for row in sqlite_connection.execute(sql)}
        if len(actual) != len(source_rows):
            raise ValueError(f"{table}: 记录数量不同，Access={len(source_rows)}, SQLite={len(actual)}")
        source_ids = [row[0] for row in source_rows]
        if len(set(source_ids)) != len(source_ids) or set(source_ids) != set(actual):
            raise ValueError(f"{table}: 原始主键重复或目标主键集合不一致")
        for row in source_rows:
            record_id = row[0]
            expected = {
                target: convert_value(row[i], kind, table, record_id, target)
                for i, target, kind in selected
            }
            for index, name in enumerate(target_names):
                if actual[record_id][index] != expected[name]:
                    raise ValueError(f"{table}[{record_id}].{name}: 内容不一致，源转换值={expected[name]!r}, 目标值={actual[record_id][index]!r}")
        total += len(source_rows)

    validate_image_pages(sqlite_connection)
    for table in IMAGE_GROUPS:
        for image_id, relative_path in sqlite_connection.execute(f'SELECT ID,路径 FROM "{table}"'):
            try:
                resolve_image_path(relative_path)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{table}[{image_id}].路径: {exc}") from exc
    validate_leader_text(access_connection)
    return {**structure, "rows": total}
