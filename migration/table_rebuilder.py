def rebuild_table(
    connection,
    table_name,
    create_table_sql
):
    new_table_name = table_name + "_new"

    connection.execute(
        f"""
        DROP TABLE IF EXISTS [{new_table_name}]
        """
    )

    connection.execute(
        create_table_sql.replace(
            f"[{table_name}]",
            f"[{new_table_name}]"
        )
    )

    connection.execute(
        f"""
        INSERT INTO [{new_table_name}]
        SELECT *
        FROM [{table_name}]
        """
    )

    connection.execute(
        f"""
        DROP TABLE [{table_name}]
        """
    )

    connection.execute(
        f"""
        ALTER TABLE [{new_table_name}]
        RENAME TO [{table_name}]
        """
    )

    connection.commit()