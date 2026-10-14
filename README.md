# Nekozzz

### 🐈 摸鱼也要做标书

没什么特别的程序，主要是减少重复劳动，让我上班有更多时间摸鱼。

标书可以一份接一份，重复劳动就没必要一遍接一遍了。

**Nekozzz** 是一个用 Python、PySide6 和 SQLite 开发的 Windows 桌面标书辅助工具。它不负责帮你中标，只负责让你少找几份文件、少复制几次资料、少往 Word 里塞几张图片。

项目最初只是为了让自己做标书时能省点事，后来功能越写越多，索性开源分享。

**毕竟，摸鱼的前提是先把活干完。**

Nekozzz 主要面向离线使用，业务资料保存在本地，没有联网功能。

## What's New in v0.9.4

- 启动先准备首屏，其他业务页面和 Excel/PDF/Access 模块按需加载；切页后复用页面状态。
- 人员选择直接进入多人 Word 输出，一人也能照常输出；新增证书名称、状态与姓名组合搜索，证书列表显示有效期和状态。
- 业务列表默认按 ID 升序；公司证书首次显示公司 ID=1 的全部证书；记住窗口位置、大小和最大化状态。
- Word/WPS 的窄列表格仍可能有不同的文字换行结果。

[下载 v0.9.4 Windows x64 Portable](https://github.com/1Hey-p1g/Nekozzz/releases/download/v0.9.4/Nekozzz-0.9.4-Windows-x64.zip) · [完整发行资料与源码](https://github.com/1Hey-p1g/Nekozzz/releases/tag/v0.9.4)

## What's New in v0.9.3

**新功能**

- 公司基本信息能看、能选字复制，也能在资质管理中编辑保存。
- 这次不只认 Word 了：设置中可选 Microsoft Word 或 WPS Writer，资料插入和人员 AutoFill 共用原有流程，保留 Word 功能。

**改进**

- 明确备份兼容性由备份格式与数据库结构决定，应用版本只标记来源；加强完整性、附件路径和解压校验，保留兼容的 v0.9.2 备份支持。

**已知差异**

- WPS Writer 与 Microsoft Word 的排版引擎存在差异，部分窄列表格可能出现不同的文字换行结果。

## 功能

- 人员及人员证书管理、多人资料选择
- 公司资质管理、公司基本信息查看／复制／编辑
- 工程业绩及项目管理人员管理、多项目资料选择
- 获奖及财务资料管理
- PDF 附件导入、图片预览与管理
- Microsoft Word／WPS Writer 可选目标资料输出
- 实验性人员自动填表（experimental feature）

技术栈：Python、PySide6、SQLite。文档插入目标可在设置中选择 Microsoft Word 或 WPS Writer；
请先打开所选程序及文档，不会自动启动或切换目标。Access 迁移需要匹配的 Windows Access ODBC 驱动。
Microsoft Word、WPS Writer 和 Access 驱动不随软件分发。

## Windows prerequisites

Windows 10/11 x64；运行前需要足够新的 Microsoft Visual C++ v14 x64 Runtime。
缺失时请从 [Microsoft 官方下载说明](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)安装 x64 版本。
Nekozzz 不携带 VC DLL 或安装器，也不自动下载/安装。文档输出需要桌面版 Microsoft Word 或 WPS Writer。
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
v0.9.2 验收 RC 的行为已通过开发者人工验收，其发行合规结论为 **B. READY EXCEPT FOR MANUAL PUBLICATION**，见 [v0.9.2 最终发行报告](NEKOZZZ_0.9.2_FINAL_RELEASE_CLEARANCE.md)。该结论仅适用于 v0.9.2。v0.9.3 RC1 的完整业务、Word/WPS、公司基本信息、备份恢复及 Access 迁移已由开发者人工验收通过；历史 Access 自动测试夹具仍缺失，不代表全量自动测试通过。v0.9.3 已正式发布，历史记录见 [v0.9.3 审计报告](NEKOZZZ_0.9.3_RELEASE_AUDIT.md)。当前 v0.9.4 的源码回归 294/294 与打包诊断通过，RC 已由开发者人工验收通过；发行资料见 [v0.9.4 Release](https://github.com/1Hey-p1g/Nekozzz/releases/tag/v0.9.4)，历史测试限制不代表当前测试结果。

## Development

Developed by 1Hey-p1g.

Development assisted by OpenAI Codex.
