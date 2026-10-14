# Nekozzz v0.9.4 正式发布 — 验收补充

开发者于 2026-10-15 明确确认 v0.9.4 RC 人工验收 PASS，并授权正式发布。该结论是开发者人工验收，不是自动化 Office 测试通过。下文保留 RC 构建时的历史状态和日志；后续 Git 提交/tag/上传及下载校验详见 GitHub Release 和最终发布报告。

正式三个 ZIP 只按正式名称复制，字节与已验收 RC 完全一致，EXE 未重建。ZIP 内 README_RC 等“待验收”文本属于当时快照，本补充记录优先。

---

# Nekozzz v0.9.4 RC1 — 构建与验收报告

日期：2026-10-14～15，Asia/Shanghai。

## 1. 结论

**RC BUILT — AUTOMATED CHECKS PASS — DEVELOPER EXE ACCEPTANCE PENDING**。

干净 Windows x64 onedir 构建成功；源码回归 294/294、打包诊断 97 项及最终 ZIP 解压后的未插桩 EXE 启动验证通过。本轮未发布、上传、commit、push 或创建/移动 tag。没有覆盖 v0.9.3 或其他历史资产。

开发者此前确认 0.9.4 开发源码人工验收通过；该结论不自动等于本轮 RC EXE 人工验收通过。真实 Word/WPS 写入、视觉、DPI/多显示器仍需验收。

## 2. 构建来源与编译前检查

- 实际源码目录：`E:\Python Program\TenderSystem`。当前不是 Git 仓库，`git status` 返回 not a git repository；先前记录的 `E:\Python Program\Nekozzz-release-repo` 本次不存在。
- **本 RC 无可声明的 Git 分支/commit。** 不虚构归属到 v0.9.3 commit；使用完整 SHA256 源码快照确定构建来源，正式发布前仍需关联实际 Git 提交。
- `report/release_0.9.4/source_before.json` SHA256：`715b2b1d54a10683291c1959dc4a61f7f16324a3dc48f35ebb4efbe86f4b8377`。
- 已对照启动审计、0.9.4 开发报告及人员组合搜索记录，确认懒加载、延迟导入、默认 ID 顺序、公司1、窗口几何、多人入口、证书列和组合搜索都在构建输入中。基准差异保存于 baseline_093_diff.json。
- APP_VERSION=0.9.4、DB_SCHEMA_VERSION=1、BACKUP_FORMAT_VERSION=1。主窗口/关于/备份来源使用常量。
- 人员模板 SHA256 仍为 `892ae87bd316d82448cbd297938359417b7a08650f3d40f6c3b182a803119a52`；图标、UI、schema 和已有业务模块本轮不修改。
- 扫描正式源码没有发现 breakpoint/pdb 或私人 TEMP 测试库路径。打包代码对象扫描未发现本机工作区/用户绝对路径常量或 co_filename；报告内的构建路径属于本地证据，不进入应用运行时。
- 生产源码和构建配置在任务前后保持相同哈希。没有为本轮 RC 修改 Word/WPS、XML、模板、数据库、业务行为或依赖。

环境：Python 3.14.7 x64；PyInstaller 6.22.3、hooks-contrib 2026.8、PySide6/Shiboken 6.11.2、PyMuPDF 1.28.2、openpyxl 3.1.5、pyodbc 5.3.0、pywin32 312、Pillow 12.3.0（构建/测试工具，未加入 runtime）。未升级任何依赖。

## 3. 构建流程及首轮环境差异

正式 Nekozzz.spec 的 onedir、图标、元数据、资源、hook、exclude 及既定 runtime boundary 原样使用。**没有新增 hiddenimports 或修改 spec。** 函数内 import 仍被 PyInstaller 静态分析；实际 PYZ/PE 清单确认 openpyxl、pymupdf、迁移模块、pyodbc、各懒加载 GUI 模块均存在。

第一次构建技术上成功，但边界核验发现 PATH 新增 Adoptium JDK 21，由其 bin 目录提供了 43 个非预期 API-set/UCRT DLL。与旧包不同的只有这些新增文件；COLLECT 清单明确给出来源。这次产物未用作交付。

仅在构建子进程 PATH 排除该已查明的 JDK 目录，沿用已有 build_environment 排除原 Microsoft JDK 的做法，使用新 work/dist 重建。未改变系统 PATH、生产 helper、依赖版本，也未从完成后的包手工删除 DLL。

- 最终 work：`build/release_094/candidate_isolated/work`。
- 最终 PyInstaller 输出：`build/release_094/dist_isolated/Nekozzz`。
- 交付 onedir：`release/Nekozzz-0.9.4-rc1/binary/Nekozzz`。
- 首轮产物保留于 `release/Nekozzz-0.9.4-rc1/failed_initial_build`，仅作失败证据，不在任何候选 ZIP 中。不要使用它验收。

## 4. 自动化测试

完整 `tests/`：**294 执行、294 通过、0 失败、0 错误、0 跳过，192.570 秒**。

沿用既有 Qt/QThread 测试进程 GC 隔离，默认设置路径指向 TEMP；未改变生产 GC 行为，未删测试或削弱断言。使用普通用户上下文执行 Access ODBC，真实样本仅经临时副本处理，新 SQLite 目标在 TEMP；不写原业务数据。

包括人员搜索/证书状态/组合查询、同一证书语义、任务状态/排序、导航/懒加载/主题/窗口几何、公司信息/默认公司、PDF/XLSX、Word/WPS fake COM、AutoFill 冻结 XML、备份恢复及历史格式、Access 迁移。日志：`report/release_0.9.4/full_initial.log/json`。

## 5. 打包后的验证及证据边界

原 spec 另构建诊断 twin，唯一目的为从已显示主窗口运行外部测试脚本。**交付 EXE 没有诊断 hook。** twin 与交付 RC 全部 DLL/PYD、完整 PYZ 模块代码相同；证据 diagnostic_equivalence.json。

打包诊断 **97 项 PASS**：

- 原生 Windows Qt 后端，首屏只有 PersonWordPage，无旧模式按钮；openpyxl/pymupdf/pyodbc/旧单人页尚未提前加载。
- 全部12个主导航首次访问及缓存再次访问，管理聚合页子 Tab 单独检查缓存身份。Settings/About、原图标、三主题及基础控件/滚动/分割器正常。
- 姓名+证书名+状态、有效/长期、过期、即将到期、同一证书匹配、默认 ID 顺序、有效期/状态列、无匹配清空详情而任务勾选保留、切页保留筛选。
- 公司1不存在时空结果；测试加入公司1/2后，公司1的不同证书ID全部显示且升序，主动切换公司2后保留。
- PNG/JPEG/ICO/SVG、缺图占位、三页PDF渲染/旋转/临时清理、人员XLSX导出/readback、Excel结构读取。
- **冻结解释器中的真实 Access 临时副本迁移成功**；user_version=1、integrity_check=ok，原 Access 哈希不变。
- AutoFill真实模板+附件输出计划、人员图片输出计划、模板哈希及DTD拒绝。
- 备份创建、校验、来源0.9.4、数据库/附件恢复和完整性；Word/WPS目标设置保存/readback；几何保存/恢复。
- lxml不可导入且没有加载，openpyxl正常 ElementTree fallback；没有QtNetwork从外部加载。

首轮 diagnostic 误将嵌套获奖/财务管理 Tab 作为 QStackedWidget 主导航，检查失败；仅修正诊断脚本按真实 `_page_factories` 判断，保留失败日志 packaged_smoke_attempt_1.*，没有修改程序。首轮测量脚本忘记关闭自身 SQLite连接导致 TEMP 清理失败，也只修正诊断脚本，未改业务代码。

未插桩 RC 本体另完成5次启动、窗口可见/响应/正常退出及空白Portable V1初始化；最终ZIP在普通用户上下文解压，文件哈希与交付目录相同，原 EXE 可见、退出码0、空库结构/完整性正常。handoff_verification.json 确认稳定路径可读及原始payload未变化。

**真实 Office 限制：** 当前测试上下文 Word GetActiveObject 返回 HRESULT -2147221021，WPS返回 -2147221005（无效类字符串），未执行真实内容插入。fake COM、计划或 GUI 设置 PASS 不等于真实 Word/WPS 格式通过；留给开发者人工验收。没有保存、关闭或修改用户 Office 文档。

## 6. 运行时边界与资源

- DLL 24，PYD 32；所有这些文件 SHA256 与 v0.9.3 RC 原包相同。
- Qt Core/Gui/Widgets/UiTools/OpenGLWidgets/OpenGL/Svg；插件仅 qwindows、qmodernwindowsstyle、qjpeg、qico、qsvg、qsvgicon。
- 没有 opengl32sw、QtNetwork/TLS/NetworkInformation、可选 image plugins、lxml runtime，未加入新 native 组件。
- PyMuPDF native 组件保留；无 VC Runtime DLL 或 vc_redist 安装器私有拷贝。加载的 VCRUNTIME140/MSVCP140 来自 Windows System32，本机前提满足。
- GIF/WebP/TIFF失败为已接受的格式政策 EXPECTED LOSS，不是本次回归。
- 生产 PYZ 与冻结源码编译结果的关键结构/字节码一致，比较包含字节码、常量、引用名称、变量、参数、flags、行号及异常表，不比较构建路径；详见 packaged_source_correspondence.json。
- 交付树没有 .db/.accdb/.mdb/.pdf、settings.json、私钥或测试图像。database/Images/config/Backups 为空。首次运行才创建空白Portable数据。
- 包含只读 personnel_table.docx、DatabaseStructure.xlsx、图标及原许可证；Office资源不做metadata改写。

## 7. EXE 启动性能

未插桩 RC TEMP 副本，Windows平台，~10ms轮询；起点是创建进程请求，终点分别为可见的 Nekozzz HWND 和随后 WM_NULL 响应，不是物理首次绘制或完整业务交互。

| 次数 | 场景 | 窗口可见 ms | 消息响应 ms |
|---|---|---:|---:|
| 1 | 预创建空白DB，首个样本 | 1066.100 | 1070.050 |
| 2 | 同空白DB，再次启动 | 555.599 | 557.626 |
| 3 | 同空白DB，再次启动 | 555.628 | 558.142 |
| 4 | Portable首次创建空库 | 568.301 | 573.681 |
| 5 | Portable再次启动 | 557.723 | 559.321 |

前三次沿用旧审计的预创建空DB口径。旧0.9.3记录约1672/1266/1257ms；本次为1066/556/556ms，但不同日期/系统缓存/设置/构建环境，非严格配对A/B，不给出改善百分比承诺。第四次是数据意义上的首次启动，此时文件缓存已被前几次预热，不能称“冷启动”。

旧源码offscreen约248ms与本次EXE测量分开记录，不作为EXE时间。PyInstaller引导/Python导入/Qt初始化/首次绘制未在本体内单独插桩，不能从两个时间差推算各阶段开销。WM_NULL响应只说明该窗口消息处理可响应，不代替全部页面/Office可交互验收。

## 8. 交付物与 SHA256

稳定 RC 根目录：`E:\Python Program\TenderSystem\release\Nekozzz-0.9.4-rc1`。

EXE：`binary/Nekozzz/Nekozzz.exe`，SHA256：
`7292cffacaa0a8e0dbea4b6a52d13aa32f772c1797e746e2faec7975ade4d1c3`。

最终onedir：**1020文件、24 DLL、32 PYD、133,412,642字节**。

| 附件 | 字节 | SHA256 |
|---|---:|---|
| Nekozzz-0.9.4-rc1-Windows-x64.zip | 57,998,785 | 9208bfbf1901e8221444415aa76ecbfb1951928eb53064a1dabdc1b9945a58a8 |
| Nekozzz-0.9.4-rc1-source.zip | 2,845,760 | c3d2d39d7f992827016ae0e8187f899ef34f37d105e44f5264008417a3db05a1 |
| Nekozzz-0.9.4-rc1-corresponding-source.zip | 413,807,410 | 93face3c47116b31f76ce83d1774e775d58e5ee6bf3a6b1cdc1920a002974668 |

Portable ZIP 根目录为 Nekozzz/，所有成员CRC及逐文件SHA256已核验，再实际解压启动。源码按白名单复制，无真实业务数据；包含必要代码/测试/资源/spec/锁定依赖和构建helper。Access私有样本不在源码包，因此源码包测试环境需另提供合法夹具。

第三方对应源码ZIP从0.9.3材料逐字节复制、内部upstream archives按既有index逐个hash复核；版本/native全相同，复用依据明确，历史companion记录未伪改。不重新声称完成新一轮全面许可证审计。最终发布前仍需关联提交、实际发布源码及校验公众下载访问。

RC 仅对随附文档更新0.9.4标题/状态，补充 README_RC、Patch Notes、RC_SOURCE_MAP及当前application index；内部未变的历史资料明确是历史证据。根README/原合规文档保持原字节。本轮没有二进制或生产源码修复。

Patch Notes：`NEKOZZZ_0.9.4_RELEASE_NOTES.md`，中文完整，按实际变化编写，无性能保证、无新AutoFill功能、无专利表、无重复列举0.9.3已有WPS为新增功能。

清单：SHA256SUMS.txt、RC_FILE_INVENTORY.json、APPLICATION_SOURCE_MANIFEST.json。机器证据：`report/release_0.9.4/`。

## 9. 人工验收与下一步

请在新目录解压Portable ZIP，不覆盖现有安装。使用合成/测试资料：

1. 启动、图标/版本/主窗口；遍历全部导航首次与再次访问，Settings/About。
2. 姓名/证书名称/状态组合与清除；同证书条件；一人/多人任务、顺序、勾选/附件在筛选与切页后保留。
3. 公司1全部证书、没有公司1空结果、主动切换公司及筛选保持。
4. System/Light/Dark，窗口大小/位置/最大化关闭重启恢复，实际DPI/多显示器。
5. PDF导入/预览、XLSX导出/读回、测试Access迁移、备份恢复/重启数据保持。
6. 分别明确选择Word/WPS活动文档，所有资料业务入口、一人/多人、AutoFill、图片、标题/注释/姓名/附件、顺序/分页/光标、保存重开；核对既有窄列表格换行差异。

**停止在EXE人工验收阶段。** 没有生成GitHub Release、上传、tag或push。收到明确发布授权前不进入正式发布。
