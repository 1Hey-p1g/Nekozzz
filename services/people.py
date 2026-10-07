"""People and certificate rules shared by the two GUI pages."""

import sqlite3
import re
from datetime import date

from repositories.person_repository import PERSON_FIELDS, PersonRepository
from repositories.certificate_repository import CERTIFICATE_FIELDS, CERTIFICATE_PRIORITY, CertificateRepository


EXPIRING_SOON_DAYS = 30  # Old Access VBA classified dates before Date()+30 as imminent.
_IDENTITY_REGIONS = {
    "11", "12", "13", "14", "15", "21", "22", "23", "31", "32", "33", "34", "35", "36", "37",
    "41", "42", "43", "44", "45", "46", "50", "51", "52", "53", "54", "61", "62", "63", "64", "65",
    "71", "81", "82",
}
_IDENTITY_CHECK_CODES = "10X98765432"
_IDENTITY_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)


def gender_from_identity(identity):
    """Gender from position 17 of an 18-character mainland identity number.

    This only validates the number's shape; age retains its existing checksum
    and birth-date validation. Unknown/legacy numbers produce no derived value.
    """
    if not isinstance(identity, str):
        return None
    number = identity.strip()
    if not re.fullmatch(r"[0-9]{17}[0-9Xx]", number):
        return None
    return "男" if int(number[16]) % 2 else "女"


def age_from_identity(identity, today=None):
    """Full years from a valid Chinese 18-digit ID (or legacy 15-digit ID)."""
    today = today or date.today()
    if not isinstance(identity, str):
        return None
    value = identity.strip().upper()
    if value[:2] not in _IDENTITY_REGIONS:
        return None
    if re.fullmatch(r"\d{17}[\dX]", value):
        checksum = _IDENTITY_CHECK_CODES[sum(int(a) * b for a, b in zip(value[:17], _IDENTITY_WEIGHTS)) % 11]
        if value[-1] != checksum:
            return None
        birthday = value[6:14]
    elif re.fullmatch(r"\d{15}", value):
        birthday = "19" + value[6:12]
    else:
        return None
    try:
        born = date.fromisoformat(f"{birthday[:4]}-{birthday[4:6]}-{birthday[6:]}")
    except ValueError:
        return None
    if born > today:
        return None
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def work_years(start, today=None):
    """Full years since entering this company; no derived value is persisted."""
    today = today or date.today()
    if not isinstance(start, str):
        return None
    try:
        entered = date.fromisoformat(start)
    except ValueError:
        return None
    if entered.isoformat() != start or entered > today:
        return None
    return today.year - entered.year - ((today.month, today.day) < (entered.month, entered.day))


def expiry_status(raw, today=None):
    today = today or date.today()
    if raw is None:
        return "长期有效"
    if raw == "":
        return "未填写或无法判断"
    try:
        end = date.fromisoformat(raw)
    except (TypeError, ValueError):
        return "未填写或无法判断"
    if end < today:
        return "已过期"
    if (end - today).days < EXPIRING_SOON_DAYS:
        return "即将到期"
    return "正常有效"


def _date_or_none(value, field):
    if value is None or value == "":
        return None
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field}必须是有效的 YYYY-MM-DD 日期") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{field}必须使用 YYYY-MM-DD 格式")
    return value


def validate_person(values):
    result = {field: values.get(field) for field in PERSON_FIELDS}
    result["姓名"] = (result["姓名"] or "").strip()
    if not result["姓名"]:
        raise ValueError("姓名不能为空")
    result["进入系统日期"] = _date_or_none(result["进入系统日期"], "入职日期")
    return result


def validate_certificate(values):
    result = {field: values.get(field) for field in CERTIFICATE_FIELDS}
    if not isinstance(result["人员ID"], int) or result["人员ID"] <= 0:
        raise ValueError("请选择人员")
    result["证书名称"] = (result["证书名称"] or "").strip()
    if not result["证书名称"]:
        raise ValueError("证书名称不能为空")
    result["有效期"] = _date_or_none(result["有效期"], "证书有效期")
    return result


def deletion_blockers(dependencies):
    return "、".join(f"{name} {count} 条" for name, count in dependencies.items() if count)


def friendly_database_error(error):
    if isinstance(error, sqlite3.IntegrityError):
        return f"数据库约束拒绝本次操作：{error}。请先处理关联记录，数据未保存。"
    return str(error)


class PeopleService:
    def __init__(self, database_path):
        self.people = PersonRepository(database_path)
        self.certificates = CertificateRepository(database_path)

    def add_person(self, values):
        return self.people.add(validate_person(values))

    def update_person(self, person_id, values):
        self.people.update(person_id, validate_person(values))

    def delete_person(self, person_id):
        blockers = deletion_blockers(self.people.dependencies(person_id))
        if blockers:
            raise ValueError(f"无法删除人员：仍有关联的{blockers}")
        self.people.delete(person_id)

    def add_certificate(self, values):
        return self.certificates.add(validate_certificate(values))

    def update_certificate(self, certificate_id, values):
        self.certificates.update(certificate_id, validate_certificate(values))

    def delete_certificate(self, certificate_id):
        blockers = deletion_blockers(self.certificates.dependencies(certificate_id))
        if blockers:
            raise ValueError(f"无法删除证书：仍有关联的{blockers}")
        self.certificates.delete(certificate_id)

    def selected_certificates(self, certificate_ids):
        """Stable IDs for the future Word module, with current V1 records and pages."""
        result = []
        for certificate_id in dict.fromkeys(certificate_ids):
            row = self.certificates.get(certificate_id)
            if row:
                result.append({**row, "附件": self.certificates.attachments(certificate_id)})
        priorities = {name: index for index, name in enumerate(CERTIFICATE_PRIORITY)}
        return sorted(result, key=lambda row: (
            row["人员ID"], priorities.get(row["证书类型"], 99),
            row["证书类型"] or "", row["证书名称"], row["证书ID"],
        ))
