from migration.excel_structure_reader import (
    get_table_fields,
    get_primary_key_fields
)



def delete_rows(
        connection,
        table_name,
        field_name,
        value
):
    sql = f"""
        DELETE FROM [{table_name}]
        WHERE [{field_name}] = ?
    """

    cursor = connection.execute(
        sql,
        (value,)
    )

    return cursor.rowcount



def delete_parent_and_children(
    connection,
    relationships,
    parent_table,
    parent_field,
    parent_value
):
    try:

        connection.execute(
            "BEGIN"
        )

        for relationship in relationships:

            if relationship["parent_table"] != parent_table:
                continue

            child_table = relationship["child_table"]
            child_field = relationship["child_field"]

            delete_rows(
                connection,
                child_table,
                child_field,
                parent_value
            )

        deleted_count = delete_rows(
            connection,
            parent_table,
            parent_field,
            parent_value
        )

        connection.commit()

        return deleted_count

    except Exception:

        connection.rollback()

        raise



def get_child_ids(
    connection,
    relationship,
    parent_value
):
    child_table = relationship["child_table"]
    child_field = relationship["child_field"]

    sql = f"""
        SELECT [{child_field}]
        FROM [{child_table}]
        WHERE [{child_field}] = ?
    """

    cursor = connection.execute(
        sql,
        (parent_value,)
    )

    rows = cursor.fetchall()

    return [row[0] for row in rows]



def get_child_primary_keys(
    connection,
    relationship,
    parent_value,
    child_primary_key
):
    child_table = relationship["child_table"]
    child_field = relationship["child_field"]

    sql = f"""
        SELECT [{child_primary_key}]
        FROM [{child_table}]
        WHERE [{child_field}] = ?
    """

    cursor = connection.execute(
        sql,
        (parent_value,)
    )

    rows = cursor.fetchall()

    return [row[0] for row in rows]



def delete_record_recursive(
    connection,
    relationships,
    primary_keys,
    table_name,
    primary_value
):
    child_relationships = []

    for relationship in relationships:

        if relationship["parent_table"] == table_name:

            child_relationships.append(
                relationship
            )

    for relationship in child_relationships:

        child_table = relationship["child_table"]
        child_field = relationship["child_field"]

        child_primary_key = primary_keys[child_table]

        child_ids = get_child_primary_keys(
            connection,
            relationship,
            primary_value,
            child_primary_key
        )

        for child_id in child_ids:

            delete_record_recursive(
                connection,
                relationships,
                primary_keys,
                child_table,
                child_id
            )

    primary_key = primary_keys[table_name]

    delete_rows(
        connection,
        table_name,
        primary_key,
        primary_value
    )



def delete_record_recursive_transaction(
    connection,
    relationships,
    primary_keys,
    table_name,
    primary_value
):
    try:
        connection.execute("BEGIN")

        delete_record_recursive(
            connection,
            relationships,
            primary_keys,
            table_name,
            primary_value
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise