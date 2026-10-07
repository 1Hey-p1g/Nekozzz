from migration.excel_structure_reader import (
    get_table_names,
    get_table_fields,
    get_primary_key_fields,
    get_relationships,
    get_indexes
)


def load_database_schema(excel_file):
    table_names = get_table_names(excel_file)
    relationships = get_relationships(excel_file)
    indexes = get_indexes(excel_file)

    tables = {}

    for table_name in table_names:
        fields = get_table_fields(excel_file, table_name)
        primary_keys = get_primary_key_fields(fields)

        tables[table_name] = {
            "fields": fields,
            "primary_keys": primary_keys
        }

    schema = {
        "tables": tables,
        "relationships": relationships,
        "indexes": indexes
    }

    return schema