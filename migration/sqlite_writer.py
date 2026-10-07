"""Exact value conversion and explicit-column inserts for the target schema."""

from datetime import date, datetime, time
from decimal import Decimal


def convert_value(value, kind, table, record_id, field):
    """Convert a source value without losing NULL, empty text, zero or precision."""
    if value is None:
        return None
    try:
        if kind == "D":
            if isinstance(value, datetime):
                if value.time() != time.min:
                    raise ValueError("非午夜日期时间不得截断")
                return value.date().isoformat()
            if isinstance(value, date):
                return value.isoformat()
            raise TypeError("期望 Access Date/Time")
        if kind == "M":
            if not isinstance(value, Decimal):
                raise TypeError("Currency 必须为 Decimal，不得通过 float")
            scaled = value * Decimal(10000)
            if scaled != scaled.to_integral_value():
                raise ValueError("Currency 超过四位小数")
            number = int(scaled)
            if not -(2**63) <= number <= 2**63 - 1:
                raise OverflowError("超出 SQLite 64 位整数范围")
            return number
        if kind in ("I", "P"):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError("期望整数")
            return value
        if kind in ("T", "N"):
            if not isinstance(value, str):
                raise TypeError("期望文本")
            return value
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{table}[{record_id}].{field}: {exc}; 原值={value!r}") from exc
    raise ValueError(f"{table}.{field}: 未知映射类型 {kind}")


def insert_mapped_rows(connection, table, rows, mapping):
    """Insert explicit target columns using the source column order in mapping."""
    selected = [(index, target, kind) for index, (_, target, kind) in enumerate(mapping) if target]
    columns = ", ".join(f'"{target}"' for _, target, _ in selected)
    placeholders = ", ".join("?" for _ in selected)
    sql = f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})'
    for row in rows:
        record_id = row[0]
        values = [convert_value(row[index], kind, table, record_id, target) for index, target, kind in selected]
        try:
            connection.execute(sql, values)
        except Exception as exc:
            raise ValueError(f"{table}[{record_id}]: 插入目标字段失败: {exc}") from exc
