"""Create the approved 13-table SQLite schema inside the caller's transaction."""

from migration.target_schema import FOREIGN_KEYS, IMAGE_GROUPS, TABLES


def create_target_schema(connection):
    for table, (primary_key, fields) in TABLES.items():
        definitions = []
        for name, kind in fields:
            sql_type = "INTEGER" if kind.rstrip("!") in ("I", "M", "P") else "TEXT"
            if name == primary_key:
                definitions.append(f'"{name}" INTEGER PRIMARY KEY')
            else:
                required = " NOT NULL" if kind.endswith("!") else ""
                definitions.append(f'"{name}" {sql_type}{required}')
        for child, child_field, parent, parent_field in FOREIGN_KEYS:
            if child == table:
                definitions.append(
                    f'FOREIGN KEY ("{child_field}") REFERENCES "{parent}" ("{parent_field}") '
                    'ON UPDATE RESTRICT ON DELETE RESTRICT'
                )
        if table == "人员业绩表":
            # Python str.isspace characters, expressed as SQLite character codes.
            whitespace = "char(9,10,11,12,13,28,29,30,31,32,133,160,5760,8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,8232,8233,8239,8287,12288)"
            definitions += [
                'UNIQUE ("人员ID", "业绩ID", "担任角色")',
                f'CHECK (length(trim("担任角色", {whitespace})) > 0 '
                f'AND "担任角色" = trim("担任角色", {whitespace}))',
            ]
        if table == "公司业绩表":
            definitions.append('CHECK ("合同金额_scaled" IS NULL OR typeof("合同金额_scaled") = \'integer\')')
        if table in IMAGE_GROUPS:
            if dict(fields)["备注"] == "N":
                definitions.append('CHECK ("备注" IS NULL OR ("备注" <> \'\' AND "备注" NOT GLOB \'*[^0-9]*\'))')
            else:
                definitions.append('CHECK ("备注" IS NULL OR "备注" >= 0)')
        connection.execute(f'CREATE TABLE "{table}" (\n  ' + ',\n  '.join(definitions) + '\n)')

    connection.execute(
        'CREATE UNIQUE INDEX "ux_人员业绩_单项目负责人" ON "人员业绩表" ("业绩ID") '
        "WHERE \"担任角色\" = '项目负责人'"
    )
    connection.execute('CREATE INDEX "ix_人员业绩_人员角色" ON "人员业绩表" ("人员ID", "担任角色", "业绩ID")')
    connection.execute('CREATE INDEX "ix_人员业绩_工程角色" ON "人员业绩表" ("业绩ID", "担任角色", "人员ID")')
    for table, group in IMAGE_GROUPS.items():
        prefix = ', '.join(f'"{name}"' for name in group)
        expression = 'CAST("备注" AS INTEGER)' if dict(TABLES[table][1])["备注"] == "N" else '"备注"'
        connection.execute(
            f'CREATE UNIQUE INDEX "ux_{table}_页序" ON "{table}" ({prefix}, {expression}) '
            f'WHERE "备注" IS NOT NULL AND {expression} > 0'
        )
        connection.execute(f'CREATE INDEX "ix_{table}_排序" ON "{table}" ({prefix}, {expression}, "ID")')
    for child, field, _, _ in FOREIGN_KEYS:
        if child in IMAGE_GROUPS or child == "人员业绩表":
            continue
        connection.execute(f'CREATE INDEX "ix_{child}_{field}" ON "{child}" ("{field}")')
