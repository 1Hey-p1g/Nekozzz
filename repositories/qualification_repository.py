"""V1 company qualification queries and CRUD; selection stays in the GUI."""

from database.runtime import runtime_connection
from repositories.person_repository import _escape_like


QUALIFICATION_FIELDS = ('公司ID', '资质证书名称', '资质等级', '发证机构', '发证日期', '有效期')
COMPANY_FIELDS = ('公司名称', '单位性质', '地址', '成立日期', '经营期限', '经营范围',
                  '统一社会信用代码', '工商注册号', '纳税人识别号', '组织机构代码',
                  '开户行', '单位账号', '电话', '传真', '网址', '上一年基本信息')


class QualificationRepository:
    def __init__(self, database_path):
        self.database_path = database_path

    def companies(self):
        with runtime_connection(self.database_path) as connection:
            return [dict(row) for row in connection.execute(
                'SELECT 公司ID,公司名称 FROM 公司信息表 ORDER BY 公司名称,公司ID')]

    def company_info(self, company_id):
        with runtime_connection(self.database_path) as connection:
            row = connection.execute('SELECT * FROM 公司信息表 WHERE 公司ID=?',
                                     (company_id,)).fetchone()
            return dict(row) if row else None

    def save_company(self, company_id, values):
        parameters = tuple(values[field] for field in COMPANY_FIELDS)
        with runtime_connection(self.database_path, write=True) as connection:
            connection.execute('BEGIN IMMEDIATE')
            if company_id is None:
                return connection.execute(
                    'INSERT INTO 公司信息表(' + ','.join(COMPANY_FIELDS) + ') VALUES(' +
                    ','.join('?' for _ in COMPANY_FIELDS) + ')', parameters).lastrowid
            cursor = connection.execute(
                'UPDATE 公司信息表 SET ' + ','.join(field + '=?' for field in COMPANY_FIELDS) +
                ' WHERE 公司ID=?', (*parameters, company_id))
            if cursor.rowcount != 1:
                raise LookupError(f'公司 ID {company_id} 不存在')
            return company_id

    def search(self, name='', grade='', company_id=None):
        conditions = ['Q.资质证书名称 LIKE ? ESCAPE \'\\\'', 'COALESCE(Q.资质等级,\'\') LIKE ? ESCAPE \'\\\'']
        parameters = [f'%{_escape_like(name.strip())}%', f'%{_escape_like(grade.strip())}%']
        if company_id is not None:
            conditions.append('Q.公司ID=?')
            parameters.append(company_id)
        with runtime_connection(self.database_path) as connection:
            return [dict(row) for row in connection.execute(
                'SELECT Q.*,C.公司名称 FROM 公司资质表 Q JOIN 公司信息表 C ON C.公司ID=Q.公司ID '
                'WHERE ' + ' AND '.join(conditions) + ' ORDER BY Q.资质证书名称,Q.资质等级,Q.资质ID', parameters)]

    def get(self, qualification_id):
        with runtime_connection(self.database_path) as connection:
            row = connection.execute(
                'SELECT Q.*,C.公司名称 FROM 公司资质表 Q JOIN 公司信息表 C ON C.公司ID=Q.公司ID '
                'WHERE Q.资质ID=?', (qualification_id,)).fetchone()
            return dict(row) if row else None

    def list_names(self):
        with runtime_connection(self.database_path) as connection:
            return sorted({row[0].strip() for row in connection.execute(
                'SELECT DISTINCT 资质证书名称 FROM 公司资质表') if row[0] and row[0].strip()})

    def attachments(self, qualification_id):
        with runtime_connection(self.database_path) as connection:
            return [dict(row) for row in connection.execute(
                'SELECT ID,资质ID,路径,备注 FROM 公司资质图表 WHERE 资质ID=? '
                'ORDER BY CASE WHEN 备注 IS NULL THEN 0 ELSE CAST(备注 AS INTEGER) END,ID',
                (qualification_id,))]

    def save(self, qualification_id, values):
        parameters = tuple(values[field] for field in QUALIFICATION_FIELDS)
        with runtime_connection(self.database_path, write=True) as connection:
            if qualification_id is None:
                return connection.execute(
                    'INSERT INTO 公司资质表(公司ID,资质证书名称,资质等级,发证机构,发证日期,有效期) '
                    'VALUES(?,?,?,?,?,?)', parameters).lastrowid
            cursor = connection.execute(
                'UPDATE 公司资质表 SET 公司ID=?,资质证书名称=?,资质等级=?,发证机构=?,发证日期=?,有效期=? '
                'WHERE 资质ID=?', (*parameters, qualification_id))
            if cursor.rowcount != 1:
                raise LookupError(f'资质 ID {qualification_id} 不存在')
            return qualification_id

    def dependencies(self, qualification_id):
        with runtime_connection(self.database_path) as connection:
            return connection.execute('SELECT COUNT(*) FROM 公司资质图表 WHERE 资质ID=?',
                                      (qualification_id,)).fetchone()[0]

    def delete(self, qualification_id):
        with runtime_connection(self.database_path, write=True) as connection:
            if connection.execute('DELETE FROM 公司资质表 WHERE 资质ID=?', (qualification_id,)).rowcount != 1:
                raise LookupError(f'资质 ID {qualification_id} 不存在')
