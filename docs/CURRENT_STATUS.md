# Current Status

> Owner：交付负责人 / 产品 / 技术 / 安全 / QA
> Updated：2026-09-15
> Git baseline：M1 验收标签 `m1-accepted` → `c81a005`
> Database migration：`20260915_11` (head)
> Status：M1 ACCEPTED / M2 STARTED

## 当前事实

- M1-PRE-01、M1-01 至 M1-10、M1-CR-00 至 M1-CR-04 已完成。
- M1-A01 至 M1-A05 已关闭；M1-A06 为非阻断 P3，转入维护清单。
- M1-CR-04 已由 ADR-0005 固化归档项目写入、恢复和错误码语义。
- API/PostgreSQL 全量复验通过；总体覆盖率 89.04%，安全关键模块分支覆盖率 90.70%（78/86）。
- Staging 真实 Chromium Keycloak/BFF/Web/API/logout E2E 通过，一次性测试用户已清理。
- pip-audit、Bandit、npm audit、govulncheck 强制安全门禁通过。
- GitHub Actions run `33466902659` 对提交 `433a1ba` 为 success。
- Staging Web、API、PostgreSQL、Redis、MinIO、Keycloak 均处于 healthy。
- 产品、技术、安全、QA 四角色沿用用户账号 `ahaqu01` 的明确确认；本轮未改变签字范围或验收主体。

## 权威执行顺序

1. M1-CR-04 归档语义决策并固化契约。
2. 在同一最终提交执行 M1 完整复验与四方确认。
3. 复验文档快进进入 `main`，等待 main CI 成功并创建不可变 M1 验收标签。
4. 从已验收的 main 基线创建 `codex/m2-assets-storage`，正式启动 M2。
5. M2 严格按工作包顺序实施和逐项验收，不以“已启动”替代“已接受”。

## 决策

M1 最终复验及发布流程已完成：权威状态和复验报告已进入 `main`，main CI 成功，`m1-accepted` 与 `m1-review-remediation-accepted` 均指向 `c81a005`。M2 在独立 `codex/m2-assets-storage` 分支实施。

M2 严格按“对象 Key/威胁模型 → 存储适配端口 → 上传会话 → Multipart → 完成校验 → 下载授权 → 清理/对账 → 前端上传”推进。当前仅开放并启动 M2，不表示任何 M2 工作包已验收。

详细证据见 [M1 最终复验记录](acceptance/M1-final-reacceptance-2026-09-01.md)，归档语义见 [ADR-0005](adr/0005-archived-project-mutation-policy.md)。

## M2 当前状态

M2-00～08 与 M2-CLOSE-01～04 已完成并通过分项验收；M2-CLOSE-05 已完成产品复核、文档治理和四方角色签署，当前处于 `FOUR-PARTY ACCEPTED / MAIN RELEASE PENDING`。以下分项段落是实施证据摘要，不再表示“当前进入下一工作包”。
M2-01 设计提交为 `e69b249`，GitHub Actions run `33580267593` 为 success。
M2-02 对象存储端口和 MinIO/OSS 适配契约已通过验收；实现提交 `d4e0123`，GitHub Actions run `33581470484` 为 success。其当时遗留的真实网络 Gateway 门禁已由 M2-CLOSE-01 关闭。

M2-03 上传会话已通过验收；实现提交 `cca6a9b`，GitHub Actions run `33582996780` 为 success。迁移、PostgreSQL/RLS、配额、幂等、取消和过期门禁通过，允许进入 M2-04。
执行计划见 [M2 资产与对象存储闭环实施计划](plans/M2-assets-storage-implementation-plan.md)，启动证据见 [M2-00 验收记录](acceptance/M2-00-kickoff-gate.md)。

M2-01 决策见 [ADR-0006](adr/0006-asset-object-identity-and-lifecycle.md) 与 [M2 设计基线](design/06-M2资产与对象存储设计基线.md)，验收见 [M2-01 验收记录](acceptance/M2-01-对象Key与威胁模型-验收记录.md)。
M2-02 验收见 [对象存储适配端口验收记录](acceptance/M2-02-对象存储适配端口-验收记录.md)。
M2-03 验收见 [上传会话验收记录](acceptance/M2-03-上传会话-验收记录.md)。

M2-04 Multipart 已通过验收：实现提交 `eb78d1a`，RLS 验收修复 `b4b89d0`，GitHub Actions run `34555956515` 为 success；当前进入 M2-05。

M2-05 完成与强校验已通过验收：实现提交 `1155aae`，GitHub Actions run `34557468178` 为 success；当前进入 M2-06。

M2-06 资产访问与授权已通过验收：实现提交 `5cf93b6`，覆盖率修复 `4715aa0`，GitHub Actions run `34559105007` 为 success；当前进入 M2-07。


M2-07 清理与对账已通过验收：实现提交 `38a4e90`，迁移头 `20260915_11`，GitHub Actions run `34927350605` 为 success。过期会话、遗留 Multipart、DELETING 资产、缺失对象、孤儿对象、失败退避、SYSTEM 审计与 Outbox 门禁通过；当前进入 M2-08。


M2-08 Web 上传闭环已验收：实现提交 `faf08b4`，Web 分块摘要、Multipart、进度、暂停/恢复、取消、失败重试、资产列表/详情和授权下载通过。真实 MinIO 与阿里云 OSS 浏览器 Staging E2E 已分别由 M2-CLOSE-02/03 关闭。


M2-CLOSE-01 安全存储 Gateway 已 ACCEPTED：实现提交 `ea748b5`、验收修复 `efe20f3`、GitHub Actions run `34964313687` success。固定 peer HTTPS transport、MinIO 运行时和真实 Multipart/读取/列举/下载/删除证据齐全；凭据切换与批准的项目范围变更见 M2-CLOSE-03。

M2-CLOSE-02 真实 MinIO 浏览器 E2E 已 ACCEPTED：实现提交 `34ead76`、矩阵提交 `b3d03ba`、中文认证断言提交 `d466b49`，GitHub Actions run `34970847263` success。真实 Chromium 已通过中文登录、组织/项目、1 KB/100 MB/1 GB 样本、暂停/恢复、取消、故障重试、强校验、资产详情及授权下载；临时用户、组织、会话、资产与对象均已清理。Demo 数据库已升级至 `20260915_11`，全栈服务 healthy。
## M2-CLOSE-03（2026-09-16）

- 结论：`ACCEPTED`（经批准的范围变更）；真实阿里云 OSS 浏览器 E2E 已通过，本平台已切换到新 Key（尾号 `8cg4`）。
- Bucket 私有且阻止公共访问；CORS 使用精确 Staging 来源，GET/PUT/HEAD，暴露 ETag。
- 100 MiB 暂停恢复、取消、1 KiB 断线重试、1 GiB Multipart、AVAILABLE/VERIFIED、下载 SHA-256 均通过。
- E2E 清理后 Bucket 对象数为 0。
- RAM 管理探测返回 403，临时 Key 无 RAM 管理权限。
- 新 Key 注入后的复验为 `1 passed (4.0m)`，API `healthy`，配置权限 `0600`，Bucket 清理后对象数为 0。
- 全工程配置审计确认项目文件旧 Key 引用为 0；所有携带 OSS 配置的 Staging 容器均为新 Key，六个 Staging 服务全部健康；Demo 仅使用隔离的本地 MinIO 凭据。
- 项目负责人确认其他服务的旧 Key 迁移与废止作为本项目范围外遗留安全风险，不再阻塞 M2-CLOSE-03；旧 Key 仍按已暴露凭据管理。M2-CLOSE-03 已关闭，允许启动 M2-CLOSE-04。

## M2-CLOSE-04（2026-09-16）

- 状态：`ACCEPTED / CLOSED`，允许启动 M2-CLOSE-05。
- 实现提交 `09c03bb` 已新增资产维护生产调度入口、PostgreSQL advisory lock 防重入、单轮超时、结构化指标/告警、心跳健康检查、配置边界及独立 Staging 服务。
- Ruff 通过；调度专项及 M2-07 回归 `14 passed`；Staging 服务 `healthy`，真实 OSS 配置下一次运行 `failures=0`，持锁时正确跳过。
- API、Web/Nginx、Keycloak、维护任务及数据库审计/Outbox 的 AK/Secret 扫描均未命中。
- 故障专项、真实 PostgreSQL RLS、真实 PostgreSQL+OSS 联合状态矩阵、过期签名、全类别敏感日志扫描、并发完成、DB 提交失败恢复及重复 reconcile 均已通过。
- 全量回归 `309 passed, 1 skipped`，显式授权的真实 OSS 用例单独执行 `1 passed`；提交 `3024674`、`de4992d` 的 CI 均 success。
- Staging API/维护服务 healthy，维护单轮 `failures=0`，Bucket 对象数 0；临时测试数据库与角色已清理。M2-CLOSE-04 已关闭，M2 总签仍等待 M2-CLOSE-05。

## M2-CLOSE-05（2026-09-16）

- 状态：`FOUR-PARTY ACCEPTED / MAIN RELEASE PENDING`，前置门禁 M2-CLOSE-01～04 均已关闭。
- 当前工作范围为资产列表/详情/授权下载产品复核、权威文档一致性治理、M2 总体验收及四方签署。
- 已确认验收索引、实施计划、M1→M2 交接快照、M2-08 和 CURRENT_STATUS 中存在过期或矛盾描述，纳入本工作包修复。
- 产品范围复核、文档治理、M2 总体验收报告和产品/技术/安全/QA 四方角色签署已完成。下一步严格执行：合并 main → main CI success → 更新最终发布证据 → 最终 main CI success → 创建 `m2-accepted` 标签。
