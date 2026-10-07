def get_table_rows(connection, table_name, fields):

    cursor = connection.cursor()

    if not fields:
        raise ValueError(f"{table_name}: 必须显式指定 Access 源字段")
    columns = ", ".join(f"[{name}]" for name in fields)
    cursor.execute(f"SELECT {columns} FROM [{table_name}]")

    rows = cursor.fetchall()

    cursor.close()

    return rows
