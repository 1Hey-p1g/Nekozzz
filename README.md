# Nekozzz

摸鱼也要做标书

Nekozzz 0.9.2 是一个 Windows 桌面应用，用于管理投标／标书相关资料和文档工作流。
这是个人开源项目，主要面向离线使用，资料保存在本地。

## 功能

- 人员及人员证书管理、多人资料选择
- 公司资质管理
- 工程业绩及项目管理人员管理、多项目资料选择
- 获奖及财务资料管理
- PDF 附件导入、图片预览与管理
- Microsoft Word 资料输出
- 实验性人员自动填表（experimental feature）

技术栈：Python、PySide6、SQLite。Word 集成目前面向桌面版 Microsoft Word，
不保证 WPS 兼容性。Access 迁移需要匹配的 Windows Access ODBC 驱动。
Microsoft Word 和 Access 驱动不随软件分发。

## Windows prerequisites

Windows 10/11 x64；运行前需要足够新的 Microsoft Visual C++ v14 x64 Runtime。
缺失时请从 [Microsoft 官方下载说明](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)安装 x64 版本。
Nekozzz 不携带 VC DLL 或安装器，也不自动下载/安装。Word 输出需要桌面版 Microsoft Word。
正式 XML 后端为 Python 标准库；openpyxl 使用自己的 ElementTree/et_xmlfile fallback。
Qt 图片支持边界为 PNG/JPEG/ICO/SVG；不保证 GIF/WebP/TIFF/ICNS/TGA/WBMP。

## 使用与构建

Windows onedir 构建说明见 [BUILD_WINDOWS.md](BUILD_WINDOWS.md)。
分发时保留完整目录，不要只复制 EXE。
首次 Portable 启动使用现有初始化机制创建空 V1 数据库。
默认文件名继续保留 `database/TenderSystem-v1.db`，避免影响既有数据兼容性。

当前 Windows x64 构建基线为 Python 3.14.7，使用锁定依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -m database.initializer --sqlite-target 'C:\path\to\new-v1.db'
.\.venv\Scripts\python.exe -B main.py --database 'C:\path\to\new-v1.db'
```

初始化目标必须尚不存在。不要使用旧正式库 `database/tender.db`。
测试使用项目外临时数据；不要批量运行根目录历史实验 `test_*.py`。
当前全量测试存在已记录的 Qt／GC 原生稳定性限制，详见发行审计报告。

业务数据库、Images、Access 原件、备份和个人设置不属于源码仓库。
资源来源已按开发者确认记录；开发者已确认允许公开现有 Office 作者元数据及结构 Excel 的本地路径；资源保持原字节。

## License

Nekozzz is licensed under the GNU Affero General Public License v3.0 only.

SPDX identifier: **AGPL-3.0-only**

Copyright © 2026 1Hey-p1g

完整文本见 [LICENSE](LICENSE)。第三方组件仍受各自许可证约束，参见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

Windows binary 发布前必须提供该发行包的对应源码，而不是只链接最新版源码。
源码与第三方 copyleft 组件交付计划见 [SOURCE_AVAILABILITY.md](SOURCE_AVAILABILITY.md)。
当前验收 RC 的行为已通过开发者人工验收。发行合规结论为 **B. READY EXCEPT FOR MANUAL PUBLICATION**：对应源码及手工发布步骤见 [最终发行报告](NEKOZZZ_0.9.2_FINAL_RELEASE_CLEARANCE.md)。旧报告描述历史发行包，不代表当前运行边界。

## Development

Developed by 1Hey-p1g.

Development assisted by OpenAI Codex.
