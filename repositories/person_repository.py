"""Parameterized access to V1 people and their dependent record counts."""

from database.runtime import runtime_connection


PERSON_FIELDS = ("姓名", "身份证号", "联系电话", "学历", "毕业院校", "专业", "进入系统日期")


class PersonRepository:
    def __init__(self, database_path):
        self.database_path = database_path

    def search(self, name="", certificate_name=""):
        with runtime_connection(self.database_path) as connection:
            return [dict(row) for row in connection.execute(
                'SELECT 人员ID,姓名,身份证号,联系电话,学历,专业 FROM 人员表 '
                'WHERE 姓名 LIKE ? ESCAPE \'\\\' AND '
                '(?=\'\' OR EXISTS (SELECT 1 FROM 人员证书表 AS C WHERE C.人员ID=人员表.人员ID '
                'AND C.证书名称 LIKE ? ESCAPE \'\\\')) '
                'ORDER BY 姓名 COLLATE NOCASE,人员ID',
                (f"%{_escape_like(name.strip())}%", certificate_name.strip(),
                 f"%{_escape_like(certificate_name.strip())}%"),
            )]

    def get(self, person_id):
        with runtime_connection(self.database_path) as connection:
            row = connection.execute('SELECT * FROM 人员表 WHERE 人员ID=?', (person_id,)).fetchone()
            return dict(row) if row else None

    def projects(self, person_id):
        """Historical roles only; never infer this tender's proposed role."""
        with runtime_connection(self.database_path) as connection:
            return [dict(row) for row in connection.execute(
                'SELECT R.ID,R.人员ID,R.业绩ID,R.担任角色,P.项目名称 '
                'FROM 人员业绩表 R JOIN 公司业绩表 P ON P.业绩ID=R.业绩ID '
                'WHERE R.人员ID=? ORDER BY P.项目名称,R.业绩ID,R.ID', (person_id,))]

    def add(self, values):
        columns = ",".join(f'"{field}"' for field in PERSON_FIELDS)
        marks = ",".join("?" for _ in PERSON_FIELDS)
        with runtime_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                f'INSERT INTO 人员表 ({columns}) VALUES ({marks})',
                tuple(values[field] for field in PERSON_FIELDS),
            )
            return cursor.lastrowid

    def update(self, person_id, values):
        assignments = ",".join(f'"{field}"=?' for field in PERSON_FIELDS)
        with runtime_connection(self.database_path, write=True) as connection:
            cursor = connection.execute(
                f'UPDATE 人员表 SET {assignments} WHERE 人员ID=?',
                (*[values[field] for field in PERSON_FIELDS], person_id),
            )
            if cursor.rowcount != 1:
                raise LookupError(f"人员 ID {person_id} 不存在")

    def dependencies(self, person_id):
        with runtime_connection(self.database_path) as connection:
            return {
                "证书": connection.execute('SELECT COUNT(*) FROM 人员证书表 WHERE 人员ID=?', (person_id,)).fetchone()[0],
                "工程任职": connection.execute('SELECT COUNT(*) FROM 人员业绩表 WHERE 人员ID=?', (person_id,)).fetchone()[0],
            }

    def delete(self, person_id):
        with runtime_connection(self.database_path, write=True) as connection:
            cursor = connection.execute('DELETE FROM 人员表 WHERE 人员ID=?', (person_id,))
            if cursor.rowcount != 1:
                raise LookupError(f"人员 ID {person_id} 不存在")


def _escape_like(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
