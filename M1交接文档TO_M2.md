# M1 交接文档 TO M2

> **历史快照说明（2026-09-16）**：本文记录 M1→M2 启动时的状态和当时下一步，不再代表当前执行状态。M2 当前权威状态见 [`docs/CURRENT_STATUS.md`](docs/CURRENT_STATUS.md)，最终证据见 [`docs/acceptance/M2-总体验收报告.md`](docs/acceptance/M2-总体验收报告.md)。以下历史正文保留，不再据此判断 M2 是否完成。

> 交接日期：2026-09-02
> 仓库：`/home/diffgram/workspace/ai_auto_platform`
> 当前分支：`codex/m2-assets-storage`
> 当前提交：`6fbffbb4152e6c916d10137193198d6c042f6d28`
> M1 验收基线：`m1-accepted` → `c81a0056e27a362008ae2983f98df349f36a3120`
> 当前状态：M1 ACCEPTED / M2 STARTED

## 1. 当前任务

当前正式任务是 M2“资产与对象存储闭环”。M2-00 启动门禁已经通过，下一项只能先执行 `M2-01：对象 Key 与威胁模型`。

M2-01 的交付范围是设计和验收基线，不直接实现上传接口：

1. 定义资产状态机和状态转换约束。
2. 定义只能由服务端生成的对象 Key 规则。
3. 固定文件大小、摘要算法、内容类型、配额和生命周期边界。
4. 完成越权访问、跨租户、归档项目、预签名 URL、日志泄密和失败恢复威胁模型。
5. 输出 ADR、API 草案、数据库草案和测试矩阵。
6. 输出 `M2-01开发文档.md`、验收标准和验收记录。

在 M2-01 设计门禁通过前，不进入存储适配器、上传会话或 Multipart 实现。

## 2. 已完成内容

### 2.1 M1 功能与治理

- `M1-PRE-01`、`M1-01` 至 `M1-10` 已完成。
- 身份、BFF 会话、组织/项目 RBAC、最后 Owner 并发保护、项目生命周期、审计/幂等/Outbox、PostgreSQL RLS 和 Web 管理台闭环已落地。
- M1-A01 至 M1-A05 已关闭；M1-A06 为非阻断 P3。
- 产品、技术、安全、QA 四方确认已完成。

### 2.2 专家评审整改

- `M1-CR-00`：验收事实、主干、标签和权威状态治理闭环。
- `M1-CR-01`：身份同步并入请求事务边界，提交 `cdae4fc`。
- `M1-CR-03`：BFF staging/production 配置 fail-fast，提交 `13cf3cb`。
- `M1-CR-02`：邀请、成员角色和项目成员写操作补齐同事务审计与 Outbox，提交 `302bcc3`；测试角色修正提交 `64a2d23`。
- `M1-CR-04`：ADR-0005 固化归档项目语义，提交 `433a1ba`。

ADR-0005 的核心规则：项目归档后允许读取、恢复和受控删除；禁止业务内容、项目元数据和成员写入；冲突返回 `409 PROJECT_ARCHIVED`；恢复后成员和权限原样保留；无权主体继续遵循既有 403/404 隐藏语义。

### 2.3 M1 最终复验

- API/PostgreSQL 全量复验通过。
- 总体覆盖率 `89.04%`，安全关键模块分支覆盖率 `90.70%`（78/86）。
- 受限 PostgreSQL 运行角色保持 `NOSUPERUSER/NOBYPASSRLS`，RLS 回归通过。
- Staging 真实 Chromium Keycloak → BFF Cookie → 受保护 API → logout E2E 通过。
- 一次性 E2E 用户已删除，临时 PostgreSQL 容器已清理。
- pip-audit、Bandit、npm audit、govulncheck 通过，Critical/High 为 0。
- 整改分支最终 CI：run `33467431360`，success。
- main 最终 CI：run `33467560344`，success。
- `main` 已快进到 `c81a005`，没有强制推送或历史改写。
- 不可变标签 `m1-accepted`、`m1-review-remediation-accepted` 均指向 `c81a005`。

### 2.4 M2 启动

- 已从 `m1-accepted` 创建 `codex/m2-assets-storage`。
- M2-00 启动提交为 `6fbffbb`。
- M2 首次 CI：run `33468006681`，success。
- 已提交 `docs/plans/M2-assets-storage-implementation-plan.md`。
- 已提交 `docs/acceptance/M2-00-kickoff-gate.md`。
- 当前仓库工作区干净，分支已跟踪远端同名分支。

## 3. 当前卡住的问题与开放风险

### 3.1 当前阻塞

目前没有阻塞 M2-01 的技术问题。对象 Key、状态机和威胁模型可以立即开始。

以下事项会影响后续工作包，但不阻塞 M2-01：

1. 阿里云 OSS Staging 的 endpoint、bucket、RAM 权限和临时凭据机制尚未形成验收证据；它会阻塞 M2 的 OSS 适配与 Staging E2E，不能用 MinIO 结果替代。
2. 当前 Staging 入口仍是可信局域网/SSH 隧道内的 HTTP 语义，不是公网生产 TLS；不得把当前入口标记为生产就绪。
3. Outbox publisher 和幂等消费者尚未实现，属于后续事件交付/任务里程碑；M2 只复用 Outbox 可靠写入基线。
4. `M1-CR-05` 仍是维护清单：数据库枚举 CHECK、邮箱 downgrade 重复数据前置检查、软删除后 project code 复用决策、readiness 分级、Starlette/httpx 弃用路径等。
5. `docs/CURRENT_STATUS.md` 的 `Git baseline` 元数据仍写 `433a1ba`，而正式 M1 验收标签实际指向 `c81a005`。正文结论和标签事实正确，但下一次文档治理提交应把该字段修正为 `c81a005`，避免审计歧义。

### 3.2 禁止误判

- `M2 STARTED` 只表示入口门禁通过，不表示 M2-01～08 已实现。
- 当前没有资产表、上传会话、Multipart、下载授权或清理对账业务实现。
- MinIO 容器 healthy 不等于对象存储业务闭环已验收。
- M1 的审计/Outbox 数据写入通过不等于 Outbox publisher 已交付。
- 当前 Staging healthy 不等于生产 TLS、备份/PITR、SBOM 或镜像签名已完成。

## 4. 下一步计划

### 4.1 立即执行：M2-01

建议按以下顺序执行：

1. 盘点现有 Project、组织权限、审计、幂等、Outbox、RLS 和 MinIO 配置，不先写上传代码。
2. 建立资产状态机，至少覆盖 `PENDING_UPLOAD`、`UPLOADING`、`VERIFYING`、`AVAILABLE`、`FAILED`、`DELETING`、`DELETED`，并明确允许转换和终态。
3. 设计服务端对象 Key；Key 不包含原始文件名、邮箱、用户输入路径或可猜测租户信息，且不能由客户端指定。
4. 固定摘要算法、大小上限、内容类型策略、文件名展示字段与存储 Key 的分离。
5. 建立威胁模型：跨租户读取/写入、路径穿越、Key 覆盖、预签名泄漏、重放、超大文件、压缩炸弹、恶意内容、摘要欺骗、孤儿对象和竞态完成。
6. 定义 DB 成功/OSS 失败、OSS 成功/DB 失败、重复请求、并发完成和清理失败的恢复矩阵。
7. 将 ADR-0005 的 `409 PROJECT_ARCHIVED` 语义写入资产 API 草案，授权检查先于归档冲突判断。
8. 输出 ADR、OpenAPI 草案、ER 草案、测试矩阵、开发文档和验收记录。
9. 运行文档检查和 CI，以独立提交完成 M2-01 设计门禁。

### 4.2 后续工作包顺序

严格保持以下顺序：

1. `M2-01`：对象 Key 与威胁模型。
2. `M2-02`：对象存储适配端口，分别定义 MinIO 与 OSS 契约。
3. `M2-03`：上传会话。
4. `M2-04`：Multipart 与断点续传。
5. `M2-05`：完成校验和跨系统失败恢复。
6. `M2-06`：下载授权与短期预签名 URL。
7. `M2-07`：清理、对账和补偿。
8. `M2-08`：Web 上传闭环。

每个工作包必须有独立提交、开发文档、验收标准、验收记录和 CI 证据。只有全部工作包、真实 MinIO/OSS E2E 与四方签字通过后，才能创建 `m2-accepted`。

## 5. 验收重点

M2 总体验收至少覆盖：

- 1 KB、100 MB、1 GB 文件。
- 单段、Multipart、重复分片、断点续传、取消和会话过期。
- 正确摘要、摘要错误、大小错误、对象缺失。
- DB 成功/OSS 失败、OSS 成功/DB 失败、重复完成和并发完成。
- 跨租户 A/B/无租户、归档项目、已删除资产和越权下载。
- 预签名 URL、访问密钥、临时凭据、分片令牌不进入日志或审计 payload。
- MinIO 开发 E2E 与阿里云 OSS Staging E2E 分别提供证据。
- 审计、幂等、Outbox、RLS、清理和对账均可复现。

## 6. 版本管理要求

- 当前工作分支：`codex/m2-assets-storage`。
- 不要在 `main` 直接开发，不要强制推送，不要移动 `m1-accepted`。
- 每个工作包独立提交，避免把设计、迁移、API、Web 和运维揉成一个大提交。
- 提交前执行 `git status`、`git diff --check`、相关测试、`scripts/check_docs.py` 和完整 CI。
- PostgreSQL/RLS 变更必须使用一次性数据库或明确标识的测试数据库，禁止对共享业务库执行 destructive fixture。
- 涉及密钥、预签名、下载授权时必须增加安全扫描和日志泄漏专项测试。
- 临时容器、测试用户、测试对象和测试 bucket prefix 必须在验收后清理，并记录清理证据。

## 7. 踩过的坑

### 7.1 代码与测试

1. 项目角色枚举不存在 `EDITOR`，有效工程角色使用 `ENGINEER`。曾因测试写入 `EDITOR` 导致 PostgreSQL CI 返回 422；修复提交为 `64a2d23`。
2. 身份同步曾在鉴权依赖内部独立 `commit()`，造成请求业务事务和身份事务边界不一致。现在由请求级事务统一提交，不要重新引入依赖内提交。
3. 审计和 Outbox 必须与业务变化使用同一 session/事务；不要先提交业务再补审计事件。
4. RLS 测试必须使用 `NOSUPERUSER/NOBYPASSRLS` 运行角色；超级用户测试通过不能证明租户隔离有效。
5. E2E 必须使用真实 Chromium 和真实 Keycloak 流程；只测 service token 或接口模拟不足以关闭浏览器验收门禁。

### 7.2 环境与运维

1. 一次性 PostgreSQL 容器、Keycloak E2E 用户必须设置退出清理；命令失败也要执行 cleanup。
2. Staging 当前使用局域网 HTTP 校验语义；若切换 `APP_ENV=staging/production`，BFF public origin、callback 和 client secret 必须满足 fail-fast，公网环境必须使用 HTTPS。
3. readiness 的依赖分级尚未完全治理；不要简单把所有外部依赖串行设为硬失败，需要先区分 API 是否还能提供受限服务。
4. GitHub API 曾短暂返回 504；不要因此重复推送或重跑提交，应先根据 commit SHA 查询已有 workflow run。

### 7.3 文档、Git 与终端

1. `scripts/check_docs.py` 要求 `docs/CURRENT_STATUS.md` 包含 `## 权威执行顺序`；更新状态时必须保留该章节。
2. Git 补丁中的 hunk 行数、CRLF/LF 和文件末尾多余空行会导致 `git apply` 或 `git diff --check` 失败；提交前必须单独检查。
3. Windows PowerShell、SSH、Bash 多层引号容易破坏 SQL 和正则；复杂命令优先拆分，避免在命令行展开密钥。
4. Playwright 输出包含 Unicode 符号，在中文 Windows 控制台可能触发 GBK 编码异常；运行 SSH 辅助工具时设置 `PYTHONIOENCODING=utf-8`，并以 JSON 结果文件确认测试结论。
5. 长时间远程测试的实时输出可能在客户端等待恢复时丢失；应同时保留覆盖率 JSON、Playwright JSON、CI run 和最终检查器输出作为证据。
6. 不要把密码、Token、client secret、预签名 URL 或临时凭据写入命令输出、开发文档、Git 历史和审计 payload。

## 8. 关键文件与证据

- 权威状态：`docs/CURRENT_STATUS.md`
- M1 最终复验：`docs/acceptance/M1-final-reacceptance-2026-09-01.md`
- 归档语义：`docs/adr/0005-archived-project-mutation-policy.md`
- M2 实施计划：`docs/plans/M2-assets-storage-implementation-plan.md`
- M2 启动验收：`docs/acceptance/M2-00-kickoff-gate.md`
- M1 覆盖率证据：`coverage/m1-final.json`
- 浏览器结果：`apps/web/test-results/m1-e2e-results.json`
- main CI：`https://github.com/ahaqu01/ai_auto_platform/actions/runs/33467560344`
- M2 启动 CI：`https://github.com/ahaqu01/ai_auto_platform/actions/runs/33468006681`

## 9. 接手结论

M1 已正式关闭且不可变验收标签完整，M2 已在独立分支启动。接手人无需重复 M1 业务开发，也不要提前实现上传 API；应从 M2-01 的对象 Key、资产状态机和威胁模型开始，先完成设计门禁，再按 M2-02～08 顺序推进。
