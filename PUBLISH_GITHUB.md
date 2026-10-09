# GitHub 发布流程：Prepare → Draft → Final

本流程用于 Nekozzz 后续版本。版本、仓库、基准 tag、附件和 SHA256 从配置读取，不由脚本写死。
需要 Git、[GitHub CLI](https://cli.github.com/) 和 Python 3.11+（ZIP/source 校验仅使用标准库）。
不要在源码目录存 Token。脚本不登录、不安装、不 git init、不改变 main、不 force push、不覆盖远程 tag/附件。

## 当前 v0.9.3 状态

开发者确认 RC1 完整业务、Word/WPS、公司信息、备份和 Access 迁移人工验收 PASS。
自动化测试仍有历史 Access 夹具缺失的限制。RC1 的三个 ZIP 原字节保留；正式名字只是副本名称。
ZIP 内的 RC 准备文档是历史快照。最终人工验收由 RELEASE_AUDIT.md 与 RELEASE_NOTES.md 补充。
2026-10-10 已克隆独立仓库并创建 release/v0.9.3 分支，发布准备以最新 PUBLISH_MANIFEST.json 为准。源码同步后尚未提交；对应源码 commit 必须在另行批准的 Draft 阶段形成并核验。

## 1. 安全关联现有仓库（开发者执行）

安装 GitHub CLI 后重新打开 PowerShell，确认 `gh --version`，使用浏览器登录：

```powershell
gh auth login --hostname github.com --git-protocol https --web
gh auth status --hostname github.com
# 在新的目录克隆，不能对现有 TenderSystem 执行 git init。
git clone https://github.com/1Hey-p1g/Nekozzz.git ..\Nekozzz-release-repo
git -C ..\Nekozzz-release-repo remote -v
git -C ..\Nekozzz-release-repo tag --list v0.9.2
git -C ..\Nekozzz-release-repo switch -c release/v0.9.3
```

先比较 v0.9.2、远程当前源码和 RC1 的应用源码 ZIP，审阅差异后逐项纳入新发布分支。
保留远程已有文档/历史；不把当前工作区整个覆盖到 main，不复制 .venv、数据库、Images、Backups、个人设置或原 Access。
新工具 `tools/publish_github.ps1`、`tools/verify_release.py` 和本指南应纳入发布分支。
脚本不会替你把业务代码搬入仓库。任何不匹配先报告，不能为通过校验修改验收代码。
若只是 CRLF/LF 的 Git 换行规范化，校验会单独记录；其他代码/资源差异安全拒绝。

## 2. Prepare：只读远程检查，本地生成清单

从当前工作区执行；RepoPath 指向真正的独立 Git clone：

```powershell
.\tools\publish_github.ps1 -Action Prepare `
  -Config '.\release\Nekozzz-0.9.3-final\release-config.json' `
  -RepoPath '..\Nekozzz-release-repo'
```

本地配置及生成 manifest/state 不属于上传附件，不应提交。Prepare 校验：

- ZIP CRC、附件及成员 SHA256、完整的应用源码清单、EXE/模板、所有对应库源码归档、许可证/companion 文件。
- 三个版本和开发者人工验收声明；校验清单覆盖每一个实际上传附件。
- Git 根目录/origin/分支/HEAD、v0.9.2 tag 与远程一致、祖先关系、当前源码及明确待提交文件。
- GH 认证、公开仓库与 push 权限、目标 tag/release 冲突。
- 禁止已跟踪私有数据/虚拟环境、未审阅的工作区文件、已有暂存内容、重命名及删除。

输出 PUBLISH_MANIFEST.json 和其 SHA256。没有仓库或 gh 时会输出 BLOCKED，退出非零，不产生远程变更。
无其他 change 时直接核对当前 commit；有审阅过的 change 时生成精确提交计划，Draft 阶段确认后创建对应 commit 并再次核对，源对应关系不成立就不 push。
源码 ZIP 中仅 README/验收报告/Release Notes 可有已确认的文档状态补充；其他源码与资源仍须匹配。
历史0.9.2备份测试的两个 `.py` fixture，以及 Qt 上游许可证资料中的八个 TOML/PNG 文件被现有忽略规则排除。配置逐文件列出这十个已核验源码成员；不会放行整个 release/、业务 Images 目录或修改 .gitignore。

## 3. Publish-Draft：必须单独确认

审阅 manifest 中分支、base commit、每个提交文件、附件 hash 和操作清单。
开发者明确批准后，用 Prepare 给出的真实 manifest SHA256：

```powershell
.\tools\publish_github.ps1 -Action Publish-Draft `
  -Config '.\release\Nekozzz-0.9.3-final\release-config.json' `
  -RepoPath '..\Nekozzz-release-repo' `
  -ApprovedManifestSha256 '<Prepare 输出的完整 SHA256>' -ConfirmDraft
```

脚本仅 git add 精确审阅文件，必要时 commit；校验 commit 的源码，创建附注 tag，**仅推送该 tag，不更新远程 main**。
tag 推送会公开相应源码历史，必须包含在这次批准范围内。
然后 `gh release create --verify-tag --draft`，上传六个已批准附件；不使用 --clobber。
逐项下载全部附件验证 hash/大小/文件集合，记录 Draft URL 后停止。
已有同名 tag/release 没有本脚本匹配状态及审批 marker 时拒绝采用或覆盖。

## 4. Publish-Final：最终公开确认

Draft 的附件在公开前只能通过认证访问，因此不能声称已验证匿名公开下载。
先认证下载核验全部 binary/source/notices 附件，开发者最终确认后才公开；公开后立即执行匿名下载及 SHA256 检查。

```powershell
.\tools\publish_github.ps1 -Action Publish-Final `
  -Config '.\release\Nekozzz-0.9.3-final\release-config.json' `
  -RepoPath '..\Nekozzz-release-repo' `
  -ApprovedManifestSha256 '<同一审批清单 SHA256>' -ConfirmPublicRelease
```

再次验证 tag 对应的 commit、来源、body marker、版本、附件和权限，再 `gh release edit --draft=false --verify-tag`。
公开后匿名下载失败时会保留 PUBLIC / verification pending 状态并报告，不自动删除或回退公开发行。

## 中断与恢复

保留 PUBLISH_MANIFEST.json、release-config.json、PUBLISH_STATE.json、下载验证目录和 Git 状态。
普通上传中断可用同一审批清单重跑 Publish-Draft：只上传缺项；已存在附件必须下载 hash 相同，绝不替换。
源码 commit 或 tag 创建中断且无法证明状态归属时安全停止；检查 `git status`、`git diff --cached`、本地/远程 tag 和 state，先审阅再继续。
不要删除 tag、改 state 伪造归属、用 force 或重新 Prepare 覆盖正在发布的审批清单。
若 git add/commit 中断留下暂存内容，脚本不自动 reset，交由开发者审阅。

本轮仅验证本地 Prepare、校验器和语法/安全拒绝路径。未安装 gh、未克隆仓库，真实 commit/tag/Draft/upload/resume/公开网络流程未执行，不能称为已通过实机发布验证。

## 后续版本

为新版本新建独立附件目录及 release-config.json，填写版本/tag、基准 tag、真实 hash、源码 manifest、人工验收及明确的文件政策。
核实源码/许可证后运行同样三阶段。旧目录和校验记录不得覆盖。
官方行为参考：[Draft 与 verify-tag](https://cli.github.com/manual/gh_release_create)、[附件下载](https://cli.github.com/manual/gh_release_download)、[公开 Draft](https://cli.github.com/manual/gh_release_edit)。
