"""Certificate queries and CRUD; no GUI selection state is stored here."""

from database.runtime import runtime_connection
from repositories.person_repository import _escape_like


CERTIFICATE_PRIORITY = (
    "执业证", "职业资格注册证", "安全生产考核合格证书", "职称证", "现场管理人员证",
    "技师证", "特种作业证", "身份证", "安全生产管理人员", "特种设备管理证", "急救员证",
)
CERTIFICATE_FIELDS = ("人员ID", "证书类型", "证书名称", "证书编号", "有效期")
_ORDER = "CASE C.证书类型 " + " ".join(
    f"WHEN '{value}' THEN {index}" for index, value in enumerate(CERTIFICATE_PRIORITY, 1)
) + " ELSE 99 END, C.证书类型, C.证书名称, C.证书ID"


class CertificateRepository:
    def __init__(self, database_path):
        self.database_path = database_path

    def for_person(self, person_id, name_filter=""):
        with runtime_connection(self.database_path) as connection:
            return [dict(row) for row in connection.execute(
                'SELECT C.证书ID,C.人员ID,C.证书类型,C.证书名称,C.证书编号,C.有效期 '
                'FROM 人员证书表 AS C WHERE C.人员ID=? AND C.证书名称 LIKE ? ESCAPE \'\\\' '
                f'ORDER BY {_ORDER}',
                (person_id, f"%{_escape_like(name_filter.strip())}%"),
            )]

    def get(self, certificate_id):
        with runtime_connection(self.database_path) as connection:
            row = connection.execute('SELECT * FROM 人员证书表 WHERE 证书ID=?', (certificate_id,)).fetchone()
            return dict(row) if row else None

    def names(self):
        with runtime_connection(self.database_path) as connection:
            return [row[0] for row in connection.execute(
                'SELECT DISTINCT 证书名称 FROM 人员证书表 ORDER BY 证书名称'
            )]

    def list_certificate_types(self):
        """Read the current V1 types without storing any Settings state in SQLite."""
        with runtime_connection(self.database_path) as connection:
            values = (row[0] for row in connection.execute(
                'SELECT DISTINCT 证书类型 FROM 人员证书表'
            ))
            return sorted({value.strip() for value in values if isinstance(value, str) and value.strip()})

    def existing_ids(self, certificate_ids):
        ids = tuple(certificate_ids)
        if not ids:
            return set()
        placeholders = ",".join("?" for _ in ids)
        with runtime_connection(self.database_path) as connection:
            return {row[0] for row in connection.execute(
                f'SELECT 证书ID FROM 人员证书表 WHERE 证书ID IN ({placeholders})', ids
            )}

    def attachments(self, certificate_id):
        with runtime_connection(self.database_path) as connection:
            return [dict(row) for row in connection.execute(
                'SELECT ID,证书ID,路径,备注 FROM 人员证书图表 WHERE 证书ID=? '
                'ORDER BY CASE WHEN 备注 IS NULL THEN 0 ELSE CAST(备注 AS INTEGER) END,ID',
                (certificate_id,),
            )]

    def add(self, values):
        with runtime_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                'INSERT INTO 人员证书表 (人员ID,证书类型,证书名称,证书编号,有效期) VALUES (?,?,?,?,?)',
                tuple(values[field] for field in CERTIFICATE_FIELDS),
            )
            return cursor.lastrowid

    def update(self, certificate_id, values):
        with runtime_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                'UPDATE 人员证书表 SET 人员ID=?,证书类型=?,证书名称=?,证书编号=?,有效期=? WHERE 证书ID=?',
                (*[values[field] for field in CERTIFICATE_FIELDS], certificate_id),
            )
            if cursor.rowcount != 1:
                raise LookupError(f"证书 ID {certificate_id} 不存在")

    def dependencies(self, certificate_id):
        with runtime_connection(self.database_path) as connection:
            return {"附件": connection.execute(
                'SELECT COUNT(*) FROM 人员证书图表 WHERE 证书ID=?', (certificate_id,)
            ).fetchone()[0]}

    def delete(self, certificate_id):
        with runtime_connection(self.database_path, write=True) as connection:
            cursor = connection.execute('DELETE FROM 人员证书表 WHERE 证书ID=?', (certificate_id,))
            if cursor.rowcount != 1:
                raise LookupError(f"证书 ID {certificate_id} 不存在")
