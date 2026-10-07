"""Engineering validation. UI amounts are yuan; stored values are yuan ×10000."""

from datetime import date
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation, localcontext

from repositories.project_repository import PROJECT_FIELDS, ProjectRepository
from repositories.person_repository import PersonRepository
from services.people import deletion_blockers


@dataclass
class ProjectPersonnelEntry:
    relation_id: int | None = None
    person_id: int | None = None
    role: str = ''


def amount_to_scaled(value):
    if value is None or value == '':
        return None
    if isinstance(value, float):
        raise ValueError('合同金额不能使用浮点数')
    try:
        number = Decimal(value)
        if not number.is_finite():
            raise ValueError('请输入有限的合同金额')
        with localcontext() as context:
            context.prec = max(28, len(number.as_tuple().digits) + 4)
            scaled = number * 10000
        if scaled != scaled.to_integral_value():
            raise ValueError('合同金额最多保留四位小数')
        if not -(2**63) <= scaled < 2**63:
            raise ValueError('合同金额超出 SQLite 整数范围')
        result = int(scaled)
    except (InvalidOperation, TypeError, OverflowError) as error:
        raise ValueError('请输入有效的合同金额') from error
    if not -(2**63) <= result < 2**63:
        raise ValueError('合同金额超出 SQLite 整数范围')
    return result


def amount_text(value):
    return '' if value is None else format(Decimal(value) / Decimal(10000), 'f')


def business_date(value, label):
    if value is None or value == '':
        return value
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError()
    except (ValueError, TypeError) as error:
        raise ValueError(f'{label}必须为有效的 YYYY-MM-DD 日期') from error
    return value


class ProjectService:
    def __init__(self, database_path):
        self.projects = ProjectRepository(database_path)
        self.people = PersonRepository(database_path)

    def search(self, name='', minimum_amount='', completed_before='', started_after='', leader=''):
        return self.projects.search(name, minimum_amount=amount_to_scaled(minimum_amount),
                                    completed_before=business_date(completed_before, '竣工时间'),
                                    started_after=business_date(started_after, '开工时间'), leader=leader)

    def save(self, project_id, values, leader_id=None, *, personnel=None):
        result = {field: values.get(field) for field in PROJECT_FIELDS}
        if not isinstance(result['项目名称'], str) or not result['项目名称'].strip():
            raise ValueError('工程名称不能为空')
        result['项目名称'] = result['项目名称'].strip()
        for field in ('开工时间', '竣工时间'):
            result[field] = business_date(result[field], field)
        result['合同金额_scaled'] = amount_to_scaled(values.get('合同金额'))
        if personnel is not None:
            available = {p['人员ID'] for p in self.people.search()}
            normalized, seen, ids, leaders = [], set(), set(), 0
            for number, entry in enumerate(personnel, 1):
                prefix = f'项目管理人员第 {number} 行：'
                if type(entry.person_id) is not int or entry.person_id not in available:
                    raise ValueError(prefix + '请选择人员库中的有效人员')
                if not isinstance(entry.role, str) or not entry.role.strip():
                    raise ValueError(prefix + '担任职务不能为空')
                role = entry.role.strip()
                if (entry.person_id, role) in seen:
                    raise ValueError(prefix + '同一人员、同一职务重复')
                seen.add((entry.person_id, role))
                if role == '项目负责人':
                    leaders += 1
                    if leaders > 1:
                        raise ValueError(prefix + '同一工程最多一名项目负责人')
                if entry.relation_id is not None:
                    if type(entry.relation_id) is not int or entry.relation_id in ids:
                        raise ValueError(prefix + '关系ID无效或重复')
                    ids.add(entry.relation_id)
                normalized.append(replace(entry, role=role))
            return self.projects.save(project_id, result, None, personnel=normalized)
        # Compatibility for existing callers: only replace the leader relation.
        return self.projects.save(project_id, result, leader_id)

    def delete(self, project_id):
        blockers = deletion_blockers(self.projects.dependencies(project_id))
        if blockers:
            raise ValueError('无法删除工程：仍有关联的' + blockers)
        self.projects.delete(project_id)

    def summary(self, project_id):
        row = self.projects.get(project_id)
        if not row:
            return []
        result = []
        for field in PROJECT_FIELDS:
            value = amount_text(row[field]) if field == '合同金额_scaled' else row[field]
            result.append({'字段': '合同金额（元）' if field == '合同金额_scaled' else field,
                           '值': '—' if value is None or value == '' else str(value), '原值': value})
        result.append({'字段': '项目负责人', '值': row['项目负责人'] or '—', '原值': row['项目负责人']})
        return result
