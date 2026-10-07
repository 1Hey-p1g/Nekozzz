"""Minimal validation and RESTRICT deletion protection for reports."""

from repositories.award_finance_repository import AwardRepository, FinanceRepository


class _ReportService:
    def __init__(self, database_path):
        self.repository = self.repository_type(database_path)

    def search(self, **filters):
        return self.repository.search(**filters)

    def save(self, record_id, values):
        result = {field: values.get(field) for field in self.repository.fields}
        for field, value in result.items():
            if field == '业绩ID':
                if type(value) is not int:
                    raise ValueError('请选择关联工程')
            elif value is not None and not isinstance(value, str):
                raise ValueError(f'{field}必须是文本')
        name = result[self.repository.name_field]
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f'{self.repository.name_field}不能为空')
        # Preserve financial TEXT exactly, including whitespace, NULL and empty text.
        return self.repository.save(record_id, result)

    def delete(self, record_id):
        count = self.repository.dependencies(record_id)
        if count:
            raise ValueError(f'无法删除{self.repository.label}：仍有关联附件 {count} 条，请先处理附件。')
        self.repository.delete(record_id)


class AwardService(_ReportService):
    repository_type = AwardRepository


class FinanceService(_ReportService):
    repository_type = FinanceRepository
