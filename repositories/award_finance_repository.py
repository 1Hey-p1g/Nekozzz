"""The two V1 report domains; SQL identifiers below are fixed schema constants."""

import re

from database.runtime import runtime_connection
from repositories.person_repository import _escape_like


def year_order(value):
    """Ordering only: never convert or rewrite the stored TEXT year."""
    text = '' if value is None else str(value).strip()
    match = re.fullmatch(r'(\d{4})(?:年度|年)?', text)
    return (0, -int(match[1]), '') if match else (1, 0, text)


class _ReportRepository:
    def __init__(self, database_path):
        self.database_path = database_path

    def order_key(self, row):
        return (*year_order(row[self.year_field]), row[self.key])

    def get(self, record_id):
        with runtime_connection(self.database_path) as connection:
            row = connection.execute(self.select_sql + f' WHERE R."{self.key}"=?', (record_id,)).fetchone()
            return dict(row) if row else None

    def attachments(self, record_id):
        with runtime_connection(self.database_path) as connection:
            return [dict(row) for row in connection.execute(
                f'SELECT ID,"{self.key}",路径,备注 FROM "{self.image_table}" WHERE "{self.key}"=? '
                'ORDER BY CASE WHEN 备注 IS NULL THEN 0 ELSE CAST(备注 AS INTEGER) END,ID', (record_id,))]

    def save(self, record_id, values):
        parameters = tuple(values[field] for field in self.fields)
        with runtime_connection(self.database_path, write=True) as connection:
            if record_id is None:
                columns = ','.join(f'"{field}"' for field in self.fields)
                marks = ','.join('?' for _ in self.fields)
                return connection.execute(f'INSERT INTO "{self.table}"({columns}) VALUES({marks})', parameters).lastrowid
            assignments = ','.join(f'"{field}"=?' for field in self.fields)
            if connection.execute(f'UPDATE "{self.table}" SET {assignments} WHERE "{self.key}"=?',
                                  (*parameters, record_id)).rowcount != 1:
                raise LookupError(f'{self.label} ID {record_id} 不存在')
            return record_id

    def dependencies(self, record_id):
        with runtime_connection(self.database_path) as connection:
            return connection.execute(f'SELECT COUNT(*) FROM "{self.image_table}" WHERE "{self.key}"=?',
                                      (record_id,)).fetchone()[0]

    def delete(self, record_id):
        with runtime_connection(self.database_path, write=True) as connection:
            if connection.execute(f'DELETE FROM "{self.table}" WHERE "{self.key}"=?', (record_id,)).rowcount != 1:
                raise LookupError(f'{self.label} ID {record_id} 不存在')


class AwardRepository(_ReportRepository):
    key, table, image_table = '获奖ID', '获奖工程表', '获奖工程图表'
    fields = ('业绩ID', '获奖名称', '获奖级别', '获奖年份')
    year_field, name_field, label = '获奖年份', '获奖名称', '获奖工程'
    info_fields = ('获奖名称', '项目名称', '获奖级别', '获奖年份', '业绩ID', '获奖ID')
    select_sql = 'SELECT R.*,P.项目名称 FROM 获奖工程表 R JOIN 公司业绩表 P ON P.业绩ID=R.业绩ID'

    def search(self, name='', year='', grade='', project=''):
        fields = ('R.获奖名称', "COALESCE(R.获奖年份,'')", "COALESCE(R.获奖级别,'')", 'P.项目名称')
        conditions = [f"{field} LIKE ? ESCAPE '\\'" for field in fields]
        parameters = [f'%{_escape_like(value.strip())}%' for value in (name, year, grade, project)]
        with runtime_connection(self.database_path) as connection:
            rows = [dict(row) for row in connection.execute(
                self.select_sql + ' WHERE ' + ' AND '.join(conditions), parameters)]
        return sorted(rows, key=self.order_key)

    def projects(self):
        with runtime_connection(self.database_path) as connection:
            return [dict(row) for row in connection.execute('SELECT 业绩ID,项目名称 FROM 公司业绩表 ORDER BY 项目名称,业绩ID')]

    @staticmethod
    def title(row):
        return row['获奖名称']


class FinanceRepository(_ReportRepository):
    key, table, image_table = '年度ID', '财务报告表', '财务报告图表'
    fields = ('财务报告年度', '营业收入', '净利润')
    year_field, name_field, label = '财务报告年度', '财务报告年度', '财务报告'
    info_fields = ('财务报告年度', '营业收入', '净利润', '年度ID')
    select_sql = 'SELECT R.* FROM 财务报告表 R'

    def search(self, year=''):
        with runtime_connection(self.database_path) as connection:
            rows = [dict(row) for row in connection.execute(
                self.select_sql + " WHERE R.财务报告年度 LIKE ? ESCAPE '\\'", (f'%{_escape_like(year.strip())}%',))]
        return sorted(rows, key=self.order_key)

    @staticmethod
    def title(row):
        year = row['财务报告年度'].strip()
        if year.endswith('年度'):
            return year + '财务报告'
        if year.endswith('年'):
            year = year[:-1]
        return year + '年度财务报告'
