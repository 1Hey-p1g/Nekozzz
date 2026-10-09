"""Company qualification validation and derived expiry status."""

from datetime import date

from repositories.qualification_repository import COMPANY_FIELDS, QUALIFICATION_FIELDS, QualificationRepository
from services.people import expiry_status


class QualificationService:
    def __init__(self, database_path):
        self.qualifications = QualificationRepository(database_path)

    def search(self, *, name='', grade='', company_id=None, status=''):
        rows = self.qualifications.search(name, grade, company_id)
        result = [{**row, '有效期状态': expiry_status(row['有效期'])} for row in rows]
        return [row for row in result if not status or row['有效期状态'] == status]

    def save_company(self, company_id, values):
        result = {field: values.get(field) for field in COMPANY_FIELDS}
        for field, value in result.items():
            if value is not None and not isinstance(value, str):
                raise ValueError(f'{field}必须是文本')
        if result['公司名称'] is None:
            raise ValueError('公司名称不能为 NULL')
        raw = result['成立日期']
        if raw not in (None, ''):
            try:
                parsed = date.fromisoformat(raw)
            except (TypeError, ValueError) as error:
                raise ValueError('成立日期必须是有效的 YYYY-MM-DD 日期') from error
            if parsed.isoformat() != raw:
                raise ValueError('成立日期必须使用 YYYY-MM-DD 格式')
        return self.qualifications.save_company(company_id, result)

    def save(self, qualification_id, values):
        result = {field: values.get(field) for field in QUALIFICATION_FIELDS}
        if type(result['公司ID']) is not int:
            raise ValueError('请选择所属公司')
        name = result['资质证书名称']
        if not isinstance(name, str) or not name.strip():
            raise ValueError('资质证书名称不能为空')
        result['资质证书名称'] = name.strip()
        for field in ('资质等级', '发证机构'):
            if result[field] is not None and not isinstance(result[field], str):
                raise ValueError(f'{field}必须是文本')
        # Preserve NULL and an existing empty string; don't fill either implicitly.
        for field in ('发证日期', '有效期'):
            raw = result[field]
            if raw is None or raw == '':
                continue
            try:
                parsed = date.fromisoformat(raw)
            except (TypeError, ValueError) as error:
                raise ValueError(f'{field}必须是有效的 YYYY-MM-DD 日期') from error
            if parsed.isoformat() != raw:
                raise ValueError(f'{field}必须使用 YYYY-MM-DD 格式')
        return self.qualifications.save(qualification_id, result)

    def delete(self, qualification_id):
        count = self.qualifications.dependencies(qualification_id)
        if count:
            raise ValueError(f'无法删除资质：仍有关联附件 {count} 条，请先处理附件。')
        self.qualifications.delete(qualification_id)
