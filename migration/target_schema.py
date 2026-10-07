"""Approved SQLite target schema and explicit Access field mapping.

Excel describes the source only. The ordered definitions here are the target contract.
"""

from collections import OrderedDict


def columns(spec):
    return [(part.split(":")[0], part.split(":")[1]) for part in spec.split("|")]


TABLES = OrderedDict([
    ("公司信息表", ("公司ID", columns("公司ID:I|公司名称:T!|单位性质:T|地址:T|成立日期:D|经营期限:T|经营范围:T|统一社会信用代码:T|工商注册号:T|纳税人识别号:T|组织机构代码:T|开户行:T|单位账号:T|电话:T|传真:T|网址:T|上一年基本信息:T"))),
    ("公司资质表", ("资质ID", columns("资质ID:I|公司ID:I!|资质证书名称:T!|资质等级:T|发证机构:T|发证日期:D|有效期:D"))),
    ("公司资质图表", ("ID", columns("ID:I|资质ID:I!|路径:T!|备注:N"))),
    ("公司业绩表", ("业绩ID", columns("业绩ID:I|项目名称:T!|发包单位:T|发包单位地址:T|发包单位联系人:T|发包单位联系电话:T|开工时间:D|竣工时间:D|项目主要内容:T|合同金额_scaled:M"))),
    ("公司业绩图表", ("ID", columns("ID:I|业绩ID:I!|文件类型:T!|路径:T!|备注:P"))),
    ("人员表", ("人员ID", columns("人员ID:I|姓名:T!|身份证号:T|联系电话:T|学历:T|毕业院校:T|专业:T|进入系统日期:D"))),
    ("人员证书表", ("证书ID", columns("证书ID:I|人员ID:I!|证书类型:T|证书名称:T!|证书编号:T|有效期:D"))),
    ("人员证书图表", ("ID", columns("ID:I|证书ID:I!|路径:T!|备注:N"))),
    ("人员业绩表", ("ID", columns("ID:I|人员ID:I!|业绩ID:I!|担任角色:T!"))),
    ("获奖工程表", ("获奖ID", columns("获奖ID:I|业绩ID:I!|获奖名称:T!|获奖级别:T|获奖年份:T"))),
    ("获奖工程图表", ("ID", columns("ID:I|获奖ID:I!|路径:T!|备注:P"))),
    ("财务报告表", ("年度ID", columns("年度ID:I|财务报告年度:T!|营业收入:T|净利润:T"))),
    ("财务报告图表", ("ID", columns("ID:I|年度ID:I!|路径:T!|备注:N"))),
])

DROPPED = {
    ("公司资质表", "是否选择"),
    ("人员证书表", "是否选择"),
}
CHECK_ONLY = {("公司业绩表", "项目负责人")}
RENAMED = {("公司业绩表", "合同金额"): "合同金额_scaled"}

FOREIGN_KEYS = (
    ("公司资质表", "公司ID", "公司信息表", "公司ID"),
    ("公司资质图表", "资质ID", "公司资质表", "资质ID"),
    ("公司业绩图表", "业绩ID", "公司业绩表", "业绩ID"),
    ("人员证书表", "人员ID", "人员表", "人员ID"),
    ("人员证书图表", "证书ID", "人员证书表", "证书ID"),
    ("人员业绩表", "人员ID", "人员表", "人员ID"),
    ("人员业绩表", "业绩ID", "公司业绩表", "业绩ID"),
    ("获奖工程表", "业绩ID", "公司业绩表", "业绩ID"),
    ("获奖工程图表", "获奖ID", "获奖工程表", "获奖ID"),
    ("财务报告图表", "年度ID", "财务报告表", "年度ID"),
)

IMAGE_GROUPS = {
    "公司资质图表": ("资质ID",),
    "人员证书图表": ("证书ID",),
    "财务报告图表": ("年度ID",),
    "公司业绩图表": ("业绩ID", "文件类型"),
    "获奖工程图表": ("获奖ID",),
}


def mapping_for(source_schema):
    """Return all 85 source fields with an explicit disposition; reject drift."""
    if set(source_schema["tables"]) != set(TABLES):
        raise ValueError("Access/Excel 表清单与 13 张目标表不一致")
    actual_fk = {
        (r["child_table"], r["child_field"], r["parent_table"], r["parent_field"])
        for r in source_schema["relationships"]
    }
    if actual_fk != set(FOREIGN_KEYS):
        raise ValueError("Access/Excel 的外键关系与目标映射不一致")
    result = {}
    for table, (pk, target_fields) in TABLES.items():
        expected = {name for name, _ in target_fields}
        source_fields = source_schema["tables"][table]["fields"]
        source_names = [field["name"] for field in source_fields]
        if len(source_names) != len(set(source_names)):
            raise ValueError(f"{table}: 源字段重复")
        mapped = []
        for field in source_fields:
            name = field["name"]
            key = (table, name)
            if key in DROPPED:
                if field["data_type"] != "Yes/No":
                    raise ValueError(f"{table}.{name}: 临时选择字段源类型改变")
                mapped.append((name, None, "drop"))
            elif key in CHECK_ONLY:
                if field["data_type"] != "Text":
                    raise ValueError(f"{table}.{name}: 旧负责人文本源类型改变")
                mapped.append((name, None, "check"))
            else:
                target = RENAMED.get(key, name)
                if target not in expected:
                    raise ValueError(f"{table}.{name}: 源字段无目标映射")
                target_kind = dict(target_fields)[target].rstrip("!")
                source_type = field["data_type"]
                accepted = {
                    "I": {"Long Integer"}, "T": {"Text", "Memo", "Memo / Long Text", "Long Text"},
                    "D": {"Date/Time"}, "M": {"Currency"},
                    "N": {"Text"}, "P": {"Long Integer"},
                }
                if source_type not in accepted[target_kind]:
                    raise ValueError(f"{table}.{name}: 源类型 {source_type} 与目标 {target_kind} 不符")
                mapped.append((name, target, target_kind))
        if {target for _, target, _ in mapped if target} != expected:
            raise ValueError(f"{table}: 目标字段有缺漏或多余")
        if source_names[0] != pk or mapped[0][1] != pk:
            raise ValueError(f"{table}: 主键映射错误")
        result[table] = mapped
    if sum(map(len, result.values())) != 85 or sum(
        target is not None for rows in result.values() for _, target, _ in rows
    ) != 82:
        raise ValueError("映射字段总数不是 85→82")
    return result
