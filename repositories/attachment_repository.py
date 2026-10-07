"""V1 certificate attachment writes and cross-table file-reference checks."""

from config.paths import resolve_image_path


IMAGE_TABLES = (
    "公司资质图表", "公司业绩图表", "人员证书图表", "获奖工程图表", "财务报告图表",
)


class CertificateAttachmentRepository:
    @staticmethod
    def certificate_exists(connection, certificate_id):
        return connection.execute('SELECT 1 FROM 人员证书表 WHERE 证书ID=?', (certificate_id,)).fetchone() is not None

    @staticmethod
    def paths(connection, certificate_id):
        return [row[0] for row in connection.execute(
            'SELECT 路径 FROM 人员证书图表 WHERE 证书ID=? ORDER BY ID', (certificate_id,)
        )]

    @staticmethod
    def replace_rows(connection, certificate_id, pages):
        connection.execute('DELETE FROM 人员证书图表 WHERE 证书ID=?', (certificate_id,))
        connection.executemany(
            'INSERT INTO 人员证书图表 (证书ID,路径,备注) VALUES (?,?,?)',
            ((certificate_id, relative_path, str(number)) for number, relative_path in pages),
        )

    @staticmethod
    def delete_rows(connection, certificate_id):
        connection.execute('DELETE FROM 人员证书图表 WHERE 证书ID=?', (certificate_id,))

    parent_exists = certificate_exists

    @staticmethod
    def still_referenced(connection, relative_path, *, data_root):
        target = resolve_image_path(relative_path, data_root=data_root)
        for table in IMAGE_TABLES:
            for row in connection.execute(f'SELECT 路径 FROM "{table}"'):
                try:
                    if resolve_image_path(row[0], data_root=data_root) == target:
                        return True
                except (TypeError, ValueError):
                    continue
        return False


class ProjectAttachmentRepository(CertificateAttachmentRepository):
    """Publication protocol scoped to one (project ID, file type) group."""

    @staticmethod
    def parent_exists(connection, group):
        project_id, file_type = group
        if not isinstance(file_type, str) or not file_type.strip():
            raise ValueError('文件类型不能为空')
        return connection.execute('SELECT 1 FROM 公司业绩表 WHERE 业绩ID=?', (project_id,)).fetchone() is not None

    @staticmethod
    def paths(connection, group):
        return [row[0] for row in connection.execute(
            'SELECT 路径 FROM 公司业绩图表 WHERE 业绩ID=? AND 文件类型=? ORDER BY ID', group)]

    @staticmethod
    def delete_rows(connection, group):
        connection.execute('DELETE FROM 公司业绩图表 WHERE 业绩ID=? AND 文件类型=?', group)

    @staticmethod
    def replace_rows(connection, group, pages):
        ProjectAttachmentRepository.delete_rows(connection, group)
        connection.executemany('INSERT INTO 公司业绩图表(业绩ID,文件类型,路径,备注) VALUES(?,?,?,?)',
                               ((*group, relative, number) for number, relative in pages))


class QualificationAttachmentRepository(CertificateAttachmentRepository):
    """One complete PDF group per company qualification, with text page numbers."""

    @staticmethod
    def parent_exists(connection, group):
        return connection.execute('SELECT 1 FROM 公司资质表 WHERE 资质ID=?', group).fetchone() is not None

    @staticmethod
    def paths(connection, group):
        return [row[0] for row in connection.execute(
            'SELECT 路径 FROM 公司资质图表 WHERE 资质ID=? ORDER BY ID', group)]

    @staticmethod
    def delete_rows(connection, group):
        connection.execute('DELETE FROM 公司资质图表 WHERE 资质ID=?', group)

    @staticmethod
    def replace_rows(connection, group, pages):
        QualificationAttachmentRepository.delete_rows(connection, group)
        connection.executemany('INSERT INTO 公司资质图表(资质ID,路径,备注) VALUES(?,?,?)',
                               ((group[0], relative, str(number)) for number, relative in pages))


class AwardAttachmentRepository(CertificateAttachmentRepository):
    @staticmethod
    def parent_exists(connection, group):
        return connection.execute('SELECT 1 FROM 获奖工程表 WHERE 获奖ID=?', group).fetchone() is not None

    @staticmethod
    def paths(connection, group):
        return [row[0] for row in connection.execute('SELECT 路径 FROM 获奖工程图表 WHERE 获奖ID=? ORDER BY ID', group)]

    @staticmethod
    def delete_rows(connection, group):
        connection.execute('DELETE FROM 获奖工程图表 WHERE 获奖ID=?', group)

    @staticmethod
    def replace_rows(connection, group, pages):
        AwardAttachmentRepository.delete_rows(connection, group)
        connection.executemany('INSERT INTO 获奖工程图表(获奖ID,路径,备注) VALUES(?,?,?)',
                               ((group[0], relative, number) for number, relative in pages))


class FinanceAttachmentRepository(CertificateAttachmentRepository):
    @staticmethod
    def parent_exists(connection, group):
        return connection.execute('SELECT 1 FROM 财务报告表 WHERE 年度ID=?', group).fetchone() is not None

    @staticmethod
    def paths(connection, group):
        return [row[0] for row in connection.execute('SELECT 路径 FROM 财务报告图表 WHERE 年度ID=? ORDER BY ID', group)]

    @staticmethod
    def delete_rows(connection, group):
        connection.execute('DELETE FROM 财务报告图表 WHERE 年度ID=?', group)

    @staticmethod
    def replace_rows(connection, group, pages):
        FinanceAttachmentRepository.delete_rows(connection, group)
        connection.executemany('INSERT INTO 财务报告图表(年度ID,路径,备注) VALUES(?,?,?)',
                               ((group[0], relative, str(number)) for number, relative in pages))
