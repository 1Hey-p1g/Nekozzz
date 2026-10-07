import sqlite3
from config.paths import DATABASE_FILE


DATABASE_PATH = DATABASE_FILE


def get_connection():
    # Runtime opening must never manufacture an unversioned, schema-less file.
    # A new Portable data directory uses create_empty_database() explicitly.
    connection = sqlite3.connect(DATABASE_PATH.as_uri() + "?mode=rw", uri=True)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection

def create_company_table(connection):
    raise RuntimeError("旧建表入口已停用；新库只能通过 migration 目标 schema 新建")

def create_project_table(connection):
    raise RuntimeError("旧公司业绩建表入口已停用；不得创建含项目负责人/REAL 金额的旧表")

def insert_company(connection, company):
    
    connection.execute("""
        INSERT INTO 公司信息表 (
            公司名称,
            单位性质,
            地址,
            成立日期,
            经营期限,
            经营范围,
            统一社会信用代码,
            工商注册号,
            纳税人识别号,
            组织机构代码,
            开户行,
            单位账号,
            电话,
            传真,
            网址,
            上一年基本信息
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, company)

    connection.commit()

def get_companies(connection):

    cursor = connection.execute("""
        SELECT
            公司ID,
            公司名称,
            单位性质,
            地址
        FROM 公司信息表
    """)

    return cursor.fetchall()

def update_company_name(connection, company_id, new_name):

    connection.execute("""
         UPDATE 公司信息表
         SET 公司名称 = ? 
         WHERE 公司ID = ?
         """, (new_name, company_id))
    connection.commit()

def delete_company(connection, company_id):

    connection.execute("""
         DELETE FROM 公司信息表
         WHERE 公司ID = ?
         """,(company_id,))
    connection.commit()

#测试
if __name__ == "__main__":

     connection = get_connection()
     print("数据库连接成功")


     create_company_table(connection)
     print("公司信息表创建成功")


     companies = get_companies(connection)
     for comany in companies:
         print(comany)

     connection.close()
