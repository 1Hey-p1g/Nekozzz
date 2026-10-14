"""V1 engineering records and authoritative project leader relations."""

from database.runtime import runtime_connection
from migration.target_schema import TABLES
from repositories.person_repository import _escape_like

PROJECT_FIELDS = tuple(name for name, _ in TABLES['公司业绩表'][1] if name != '业绩ID')
_SELECT = '''SELECT P.*, L.人员ID AS 负责人ID, N.姓名 AS 项目负责人
    FROM 公司业绩表 P
    LEFT JOIN 人员业绩表 L ON L.业绩ID=P.业绩ID AND L.担任角色='项目负责人'
    LEFT JOIN 人员表 N ON N.人员ID=L.人员ID'''


class ProjectRepository:
    def __init__(self, database_path):
        self.database_path = database_path

    def search(self, name='', *, minimum_amount=None, completed_before=None, started_after=None, leader=''):
        clauses, parameters = [], []
        if name.strip():
            clauses.append("P.项目名称 LIKE ? ESCAPE '\\'")
            parameters.append('%' + _escape_like(name.strip()) + '%')
        if minimum_amount is not None:
            clauses.append('P.合同金额_scaled>=?')
            parameters.append(minimum_amount)
        if completed_before:
            clauses.append('P.竣工时间<=?')
            parameters.append(completed_before)
        if started_after:
            clauses.append('P.开工时间>=?')
            parameters.append(started_after)
        if leader.strip():
            clauses.append("N.姓名 LIKE ? ESCAPE '\\'")
            parameters.append('%' + _escape_like(leader.strip()) + '%')
        sql = _SELECT + (' WHERE ' + ' AND '.join(clauses) if clauses else '') + ' ORDER BY P.业绩ID'
        with runtime_connection(self.database_path) as connection:
            return [dict(row) for row in connection.execute(sql, parameters)]

    def get(self, project_id):
        with runtime_connection(self.database_path) as connection:
            row = connection.execute(_SELECT + ' WHERE P.业绩ID=?', (project_id,)).fetchone()
            return dict(row) if row else None

    def project_personnel(self, project_id):
        with runtime_connection(self.database_path) as connection:
            return [dict(row) for row in connection.execute(
                'SELECT R.ID AS relation_id,R.业绩ID AS project_id,R.人员ID AS person_id,'
                'N.姓名 AS person_name,R.担任角色 AS role FROM 人员业绩表 R '
                'JOIN 人员表 N ON N.人员ID=R.人员ID WHERE R.业绩ID=? '
                "ORDER BY R.ID", (project_id,))]

    def save(self, project_id, values, leader_id=None, *, personnel=None):
        with runtime_connection(self.database_path, write=True) as connection:
            connection.execute('BEGIN IMMEDIATE')
            if project_id is None:
                names = ','.join(f'"{field}"' for field in PROJECT_FIELDS)
                placeholders = ','.join('?' for _ in PROJECT_FIELDS)
                project_id = connection.execute(
                    f'INSERT INTO 公司业绩表 ({names}) VALUES ({placeholders})',
                    tuple(values[field] for field in PROJECT_FIELDS),
                ).lastrowid
            else:
                assignments = ','.join(f'"{field}"=?' for field in PROJECT_FIELDS)
                cursor = connection.execute(f'UPDATE 公司业绩表 SET {assignments} WHERE 业绩ID=?',
                                            (*[values[field] for field in PROJECT_FIELDS], project_id))
                if cursor.rowcount != 1:
                    raise LookupError(f'工程 ID {project_id} 不存在')
            if personnel is not None:
                self._sync_personnel(connection, project_id, personnel)
                return project_id
            old = connection.execute(
                "SELECT ID,人员ID FROM 人员业绩表 WHERE 业绩ID=? AND 担任角色='项目负责人'", (project_id,)
            ).fetchone()
            if old and leader_id != old['人员ID']:
                connection.execute('DELETE FROM 人员业绩表 WHERE ID=?', (old['ID'],))
            if leader_id is not None and (old is None or leader_id != old['人员ID']):
                connection.execute("INSERT INTO 人员业绩表(人员ID,业绩ID,担任角色) VALUES(?,?,'项目负责人')",
                                   (leader_id, project_id))
            return project_id

    @staticmethod
    def _sync_personnel(connection, project_id, entries):
        old = {r['ID']: r for r in connection.execute('SELECT * FROM 人员业绩表 WHERE 业绩ID=?', (project_id,))}
        # Reserve new IDs before removals so replacing a row cannot steal its ID.
        next_id = connection.execute('SELECT COALESCE(MAX(ID),0)+1 FROM 人员业绩表').fetchone()[0]
        retained = set()
        changed = []
        for number, entry in enumerate(entries, 1):
            if entry.relation_id is not None:
                if entry.relation_id not in old:
                    raise ValueError(f'项目管理人员第 {number} 行：关系不属于当前工程或已被删除')
                retained.add(entry.relation_id)
                previous = old[entry.relation_id]
                if previous['人员ID'] == entry.person_id and previous['担任角色'] == entry.role:
                    continue
            changed.append(entry)
        removed = (old.keys() - retained) | {e.relation_id for e in changed if e.relation_id is not None}
        for relation_id in removed:
            connection.execute('DELETE FROM 人员业绩表 WHERE ID=? AND 业绩ID=?', (relation_id, project_id))
        # Release old unique keys first; role/person swaps remain atomic and IDs survive.
        for entry in changed:
            relation_id = entry.relation_id
            if relation_id is None:
                relation_id, next_id = next_id, next_id + 1
            connection.execute('INSERT INTO 人员业绩表(ID,人员ID,业绩ID,担任角色) VALUES(?,?,?,?)',
                               (relation_id, entry.person_id, project_id, entry.role))

    def dependencies(self, project_id):
        with runtime_connection(self.database_path) as connection:
            return {label: connection.execute(f'SELECT COUNT(*) FROM "{table}" WHERE 业绩ID=?',
                                              (project_id,)).fetchone()[0]
                    for label, table in (('附件', '公司业绩图表'), ('人员任职', '人员业绩表'),
                                         ('关联奖项', '获奖工程表'))}

    def delete(self, project_id):
        with runtime_connection(self.database_path, write=True) as connection:
            if connection.execute('DELETE FROM 公司业绩表 WHERE 业绩ID=?', (project_id,)).rowcount != 1:
                raise LookupError(f'工程 ID {project_id} 不存在')

    def list_attachment_types(self):
        with runtime_connection(self.database_path) as connection:
            return sorted({row[0].strip() for row in connection.execute('SELECT DISTINCT 文件类型 FROM 公司业绩图表')
                           if isinstance(row[0], str) and row[0].strip()})

    def attachment_types(self, project_id):
        # Keep historical group text exactly; renaming changes its identity.
        with runtime_connection(self.database_path) as connection:
            return [dict(row) for row in connection.execute(
                'SELECT 文件类型,COUNT(*) AS 页数 FROM 公司业绩图表 WHERE 业绩ID=? '
                'GROUP BY 文件类型 ORDER BY 文件类型', (project_id,))]

    def attachments(self, project_id, file_type):
        with runtime_connection(self.database_path) as connection:
            return [dict(row) for row in connection.execute(
                'SELECT * FROM 公司业绩图表 WHERE 业绩ID=? AND 文件类型=? '
                'ORDER BY COALESCE(CAST(备注 AS INTEGER),0),ID', (project_id, file_type))]
