def get_insert_order(schema):
    """
    根据外键关系，计算数据迁移顺序。
    父表必须先于子表。
    """

    tables = list(schema["tables"].keys())
    relationships = schema["relationships"]

    # 每张表有哪些父表
    parent_tables = {}

    for table_name in tables:
        parent_tables[table_name] = set()

    for relationship in relationships:
        parent_table = relationship["parent_table"]
        child_table = relationship["child_table"]

        parent_tables[child_table].add(parent_table)

    insert_order = []

    remaining_tables = set(tables)

    while remaining_tables:

        progress = False

        for table_name in list(remaining_tables):

            parents = parent_tables[table_name]

            # 只有当所有父表都已经处理完，
            # 当前表才能进入迁移顺序
            if parents.isdisjoint(remaining_tables):

                insert_order.append(table_name)
                remaining_tables.remove(table_name)

                progress = True

        if not progress:
            raise RuntimeError(
                "无法计算迁移顺序，"
                "可能存在循环外键关系。"
            )

    return insert_order