import pyodbc
from pathlib import Path

from config.paths import PROJECT_ROOT

# =========================
# 连接 Access
# =========================
def get_access_connection(access_file):

    access_file = Path(access_file).resolve()
    if not access_file.is_file():
        raise FileNotFoundError(f"Access 文件不存在：{access_file}")
    if PROJECT_ROOT.resolve() in access_file.parents:
        raise ValueError("Access ODBC 只允许打开项目外的副本")

    connection_string = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={access_file};"
        "ReadOnly=1;"
    )

    connection = pyodbc.connect(connection_string)

    return connection

