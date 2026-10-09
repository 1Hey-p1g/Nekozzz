# Nekozzz v0.9.3 — Release Candidate 审计

## 1. Executive conclusion

**DEVELOPER MANUAL ACCEPTANCE PASS — GIT SOURCE COMMIT / DRAFT PUBLICATION BLOCKED**。本地 RC 已生成，打包 smoke PASS；不标为正式发布。
WPS 第二阶段人工验收：**PASS（开发者本次明确确认）**。此前“待验收”记录是历史状态，不能覆盖本次确认。
本轮 RC 的真实 Office 写入未执行：隔离运行上下文不能连接正在运行的 Word/WPS。
全量回归尚非全通过，具体剩余项见第4节；不能以针对性 PASS 替代缺失证据。

### 2026-10-10 开发者最终人工验收补充

**开发者人工验收：PASS**，覆盖 v0.9.3 RC1 完整业务功能、Microsoft Word / WPS Writer 文档插入、公司基本信息查看/复制/编辑/保存、备份恢复及 Access `.accdb` 迁移。
这是开发者提供的实际使用结论，不是审计脚本或自动化测试结果。人工验收补充了迁移功能使用证据，但未恢复缺失的历史 Access 测试夹具及自动覆盖；第4节原测试记录、错误及未运行项原样保留。
开发者另确认尚未克隆仓库、未安装 GitHub CLI。因此当前无可报告的分支/commit，RC1 文件哈希与源码快照关系已确定，但 Git 提交对应关系尚未确认；停止远程发布。
正式附件只复制并重命名已验收 RC1 ZIP，不重建或重打包。ZIP 内部 RC 准备文档是当时快照，最终验收记录由本报告及发布附件补充，不修改验收产物字节。

## 2. Git / 构建来源

当前目录不是 Git 仓库，无法检查分支、未提交状态、tag commit 或直接验证已发布 v0.9.2 tag。
使用保存的 `release/Nekozzz-0.9.2/source/` 作为可访问的发行源码基准，并保存变更前后文件 SHA256。
这不等于已验证 tag；开发者发布前仍须在真实仓库核对分支、差异和 tag 来源。
所有现有开发改动均保留，无 reset/commit/push/tag/upload。旧发行目录/RC 最终哈希复核单独保存。
构建输入：当前生产源码、正式 Nekozzz.spec、tools/build_pyinstaller_environment.py 和已锁定环境。
Python 3.14.7 (tags/v3.14.7:823f032, Aug  5 2026, 10:51:32) [MSC v.1944 64 bit (AMD64)]；包版本详见 environment.json。未更新任何依赖。
全新 work/dist 使用 build/release_093/，不覆盖正式 dist 或 v0.9.2。

## 3. 功能差异与实际修改

公司信息查看/选字复制/编辑保存已实现，按公司ID更新、事务回滚及跨页刷新有测试。
统一 OfficeWriterConnector 仅连接指定的已运行 Word/WPS，不自动启动、创建文档或改投另一程序。
人员、工程、资质、获奖、财务及 AutoFill 共用原业务计划和 XML/图片/排序/分页逻辑。
备份原版从未按 APP_VERSION 相等性拒绝恢复；本轮明确格式/结构版本规则并强化 ZIP/清单/附件路径/资源上限校验。
数据库版本1、备份格式1不变，人员模板 SHA256 `892ae87bd316d82448cbd297938359417b7a08650f3d40f6c3b182a803119a52` 不变。
完整基准差异见 source_baseline_diff.json；本次发布准备仅修改版本、必要文档及版本相关测试：
- tests/test_backup_compatibility.py
- tests/test_data_management.py
- tests/test_nekozzz_identity.py
- version.py
- README.md
- BUILD_WINDOWS.md
- THIRD_PARTY_NOTICES.md
- SOURCE_AVAILABILITY.md
新增发布工具/报告均非生产业务模块。既有公司/Office/备份开发代码未在发布任务中改写。
此外更新 LGPL_REPLACEMENT.md、CORRESPONDING_SOURCE_BUILD_GUIDE.md、FINAL_RELEASE_SOURCE_MAP.md、SOURCE_DELIVERY_INDEX.json；新增本报告、NEKOZZZ_0.9.3_RELEASE_NOTES.md 与 report/release_093_*.py 本地发布工具。完整源码清单单独保存，未修改 Nekozzz.spec、build_windows.ps1 或依赖锁定文件。

## 4. 自动化测试

使用无 lxml 的既有隔离 Python 环境，完整 discover tests/，仅测试进程 gc.disable，未改生产 GC。
最后一次完整运行收集 **269**，实际执行 **259**；通过 **255**，失败 **2**，错误 **3**，跳过 **0**，耗时 **463.632秒**。
其后修正身份测试中遗漏的旧About版本文字断言，身份/公司信息/Office连接/历史备份共 **28/28** 项复测通过（3.925秒、0失败/错误/跳过）。未将完整运行日志改写为全量PASS，亦未重复计算测试总数。
错误数含 setUpClass 事件，因此不能简单用 executed 减全部错误算通过数。
完整日志/traceback：report/release_0.9.3/full_tests.log、full_tests.json；首轮失败记录另行保留。
剩余失败/错误：
- test_paths_do_not_depend_on_working_directory (tests.test_migration_paths.MigrationPathTests.test_paths_do_not_depend_on_working_directory)
- test_migration_uses_only_new_external_target (tests.test_migration_paths.MigrationPathTests.test_migration_uses_only_new_external_target)
- test_odbc_can_only_open_project_outside_copy (tests.test_migration_paths.MigrationPathTests.test_odbc_can_only_open_project_outside_copy)
- setUpClass (tests.test_target_migration.TargetMigrationTests)
Access 历史夹具 `access source/Database2.accdb` 不存在。TargetMigrationTests 的10个方法因 setUpClass 未运行，非跳过、非通过。
不恢复真实业务原件、不伪造1502条样本、不删除/减弱断言。独立 V1 初始化/结构和其他迁移基础测试正常执行。
版本相关失败已修正并复测：当前版本及About文字断言更新为0.9.3；历史备份写入器加载冻结 version.py，仍断言0.9.2并实际创建/恢复ZIP。现在仅剩Access夹具相关1个失败、2个测试错误及1个setUpClass错误事件。
功能回归覆盖公司信息、人员/工程/资质/获奖财务、Office工厂、Word原语、AutoFill、PDF、设置主题、备份安全和历史格式。

## 5. RC 打包与运行证据

RC：`release/Nekozzz-0.9.3-rc1/binary/Nekozzz/Nekozzz.exe`。
构建时目录：1018 files / 24 DLL / 32 PYD / 133411003 bytes。
EXE SHA256：`84c2240bff1b8e5003989592e1df4524cadf13c579d2bc98c41066654a868823`。
元数据：ProductName/FileDescription/InternalName=Nekozzz；ProductVersion=0.9.3；FileVersion=0.9.3.0；OriginalFilename=Nekozzz.exe；Copyright © 2026 1Hey-p1g。
所有 DLL/PYD 与旧已验收 RC 逐项字节相同，无新增 native 组件。PYZ 是当前源码重建，不视为旧程序。
无 lxml package/PYD/PYZ module；历史 licenses/lxml 仅许可证证据，不是运行组件。
保留 Qt Core/Gui/Widgets/UiTools/OpenGLWidgets/OpenGL/Svg 与 qwindows/qmodernwindowsstyle/qjpeg/qico/qsvg/qsvgicon。
无 opengl32sw、QtNetwork/TLS/NetworkInformation、已移除 optional image plugin、VC DLL/installer。
PyMuPDF 1.28.2 三个 native 保留且哈希不变，其他依赖所含 zlib 等不因 lxml 消失而被宣称全局不存在。

普通未插桩 RC 在隔离 PATH、全新副本中启动并创建空 V1，user_version=1、integrity_check=ok。
诊断 twin 仅加审计 runtime hook；全部 DLL/PYD 和 PYZ模块集合一致，实际使用冻结打包模块，非源码解释器。
其 62 项检查 PASS：12导航、Settings/About/icon、三种主题、图片PNG/JPEG/ICO/SVG、文本控件、PDF渲染/旋转、XLSX、AutoFill真实模板计划、parser fail-closed、无lxml、openpyxl fallback、Word/WPS设置保存、备份创建/恢复/附件一致性。
GIF/WebP/TIFF读入失败为已接受图片边界，不是回归。模块/插件日志及系统VC加载路径见 packaged_smoke.json。
测试只写 TEMP 副本；交付目录数据库/Images/config/Backups为空。原 RC 没有加入测试业务资料。
首轮诊断脚本未关闭自建SQLite连接导致WinError32并安全回退；仅修正测试脚本连接关闭，重测PASS，生产恢复未修改。

## 6. Word / WPS 实机状态与已知差异

开发者已验收第二阶段完整GUI业务流程，确认通过。部分窄列表格可有不同换行；不补偿宽度、字体或共享XML。
本轮打包进程 read-only COM探测：
- word: Microsoft Word 连接失败（Word.Application）：(-2147221021, '操作无法使用', None, None)
- wps: WPS Writer 连接失败（KWPS.Application）：(-2147221005, '无效的类字符串', None, None)
这表示当前执行上下文不能完成 Office 写入验收，不代表开发者验收被撤销或WPS不兼容。
最终 RC 完整业务及 Office 插入已由开发者本次确认人工验收 PASS；本审计执行环境自身仍未执行真实文档写入。Mock及计划构建不冒充实机文档写入。
无第二台干净Windows测试，无缺VC系统安装前后对照，无断电恢复实验。

## 7. 依赖、许可证与源码交付

根LICENSE保持已验证AGPLv3全文SHA256 `0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0`，声明AGPL-3.0-only及开发者版权不变。
实际包/版本与 native 哈希不变，故仅复用相应0.9.2第三方证据；不是复制整体旧发行结论。
分发边界分类见 component_classification.json；CPython、OpenSSL、libffi、SQLite、Qt/PySide/Shiboken、PyMuPDF、pywin32、pyodbc、openpyxl/et_xmlfile、PyInstaller runtime notices已保留。
SQLite public domain；build-only Pillow/构建工具、历史lxml/python-docx与实际runtime区分。Word/WPS、VC及Access驱动是外部前置条件，不分发。
原始许可证树保守保留，出现历史组件notice不表示该组件仍在运行包。未引入新的第三方组件。
Qt/PySide对应源：exact pyside-setup/qtbase/qttools/qtsvg 6.11.2，含binding inputs、生成/构建及动态库替换说明。
PyMuPDF/MuPDF对应源：exact sdist、wheel-recorded Git archive、full MuPDF 1.28.2 thirdparty/resources、build record、生成参考及SWIG4.4.1流程。
这些原归档SHA256逐项复核，保留原上游文件；无下游native/library patch。不要求bit-identical重建。
仅修复构建指南中损坏的Windows示例路径；未声称执行了库重编译或替换实验。
官方参考：[AGPLv3](https://www.gnu.org/licenses/agpl-3.0.html)、[LGPLv3](https://www.gnu.org/licenses/lgpl-3.0.html)、[Qt许可](https://doc.qt.io/qt-6/licensing.html)、[Microsoft系统前置条件](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)。
本轮GNU在线获取超时，使用已保存且哈希未变的原始许可文本；Qt当前网页仅作一般参考，exact6.11.2文件许可与源档才是版本依据。
无新发现的许可证兼容性阻断项；公开对应源码下载与最终RC验收尚未履行，不标为已经发布合规。

## 8. 对应源码与隐私

本地 source/按allowlist取当前构建输入、全部tests/相关tools/资源/许可证；不包含整个开发环境、业务DB、Images、Backups、设置或Access原件。
保留历史0.9.2备份写入器及其version作为真实格式回归fixture，旧发行文件原处未改。
APPLICATION_SOURCE_MANIFEST.json标识每个源码文件，不仅引用未来main分支。
对应库源材料在 corresponding-source/；源码/库源码和二进制分开ZIP交付，SHA256SUMS.txt覆盖归档。
源码隐私扫描和 Office 元数据决策记录单独保存；既有资源披露已由开发者批准，模板未改。67个打包项目模块代码对象与当前源码编译结果相等，见 packaged_source_correspondence.json。
PyInstaller PYZ code filename检查未发现开发者工作区绝对路径；原始upstream provenance里可能保留上游构建路径，不是用户业务资料。
最终文件数/大小与ZIP校验以 final_verification.json、release_archives.json 为准，增加文档不等于runtime变更。

## 9. 最终发布待办

1. 保留历史Access夹具缺失的自动化限制；迁移实际使用已人工验收PASS，不改写为全量自动PASS。
2. 安全克隆既有GitHub仓库，在独立发布分支核对v0.9.2 tag及RC1源码，确认对应commit；当前工作区没有Git历史，不git init或强行替换main。
3. 安装并手动登录GitHub CLI，再执行tools/publish_github.ps1的Prepare，检查精确文件/操作清单。
4. 开发者确认提交、tag推送和Draft创建操作后才运行Publish-Draft；公开发布仍需独立的最终确认。目前未执行任何此类操作。
5. 同时公开匹配application source、exact库源码/companions/licenses，填写真实稳定下载URL，复核上传hash和无登录下载访问。

## 10. Evidence / output

机器可读证据：report/release_0.9.3/。发布草稿：NEKOZZZ_0.9.3_RELEASE_NOTES.md。
二进制：Nekozzz-0.9.3-rc1-Windows-x64.zip；源码：Nekozzz-0.9.3-rc1-source.zip；库源码：Nekozzz-0.9.3-rc1-corresponding-source.zip。
文件与归档hash为独立manifest，报告不嵌入自身归档hash以避免循环。
结论：RC1人工验收已完成；**当前发布停止在Git源码提交来源与CLI前置条件**。自动测试缺失覆盖如实保留。未创建Draft Release，未公开发布，未重新构建或修改RC1。
