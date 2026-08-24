# REV-01 整改双专项复审报告

- 评审日期：2026-08-24
- 评审范围：`6909d4c`（整改基线，不含）至 `f159390011036abdb9eefeb63b2fca5c264b8791`（含）
- 当前标签：`m0r-03r-01-implemented`
- 执行顺序：Bugbot → Security Review → 主评审人工复核
- 代码修改：无
- 裁决：`REMEDIATION_REQUIRED`，REV-01 未通过

## 1. 评审范围

本次复审覆盖以下已标记 `IMPLEMENTED_LOCAL` 的整改包：

- M0R-05R-01：测试数据库保险丝；
- M0R-04R-01：结构化配置校验；
- M0R-04R-02：公网地址与不可变配置；
- M0R-05R-02：PostgreSQL 断言与迁移清单；
- M0R-05R-03：API-on-PostgreSQL；
- M0R-03R-01：OpenAPI 身份语义与净化导出。

Bugbot 与 Security Review 均以只读方式执行。两个专项代理访问服务器时发生 SSH 超时，因此其发现最初基于本地保留的最终整改文件；主评审随后恢复 SSH，在当前 HEAD 上逐项核对文件、代码和准确行号。服务器工作区在复核前为干净状态。

## 2. 汇总结论

去重并经人工确认后，共有七项未关闭问题：

- P1：2 项；
- P2：5 项；
- P3：0 项。

按照整改计划“P1/P2 为 0 才能进入 REVIEWED”的门禁，REV-01 必须判定为未通过。M0R-03R、M0R-04R、M0R-05R 继续保持 `IMPLEMENTED_LOCAL`，不得升级为 `REVIEWED`、`VERIFIED_STAGING` 或 `ACCEPTED`。

## 3. 未关闭发现

### REV01-P1-01：JWKS DNS 校验与实际连接未绑定

- 来源：Bugbot P1；Security Review Medium；人工确认提升为项目 P1。
- 位置：`apps/api/src/platform_api/auth/verifier.py:42`、`apps/api/src/platform_api/common/public_network.py:34`、`:47`、`:94`。
- 证据：`validate_public_url()` 先通过 resolver 校验 DNS 结果，随后 `urllib` 仍按 hostname 再次解析并建立连接。重定向目标也采用相同的“先校验、后重新解析”模式。
- 影响：攻击者可在校验时返回公网地址、连接时返回私网/link-local 地址，绕过预期的 JWKS SSRF 防护。
- 关闭要求：连接必须固定到本次已验证 IP，同时保留原 hostname 的 TLS SNI、证书校验和 Host 语义；每个重定向 hop 重复同一过程。若采用受控出站代理，代理本身必须独立拒绝敏感网段并有集成测试。
- 状态：OPEN。

### REV01-P1-02：downgrade 目标未证明为真正可丢弃数据库

- 来源：Security Review Medium；人工按破坏性风险提升为项目 P1。
- 位置：`apps/api/tests/postgresql/safety.py:25`、`:55`，`apps/api/tests/postgresql/conftest.py:50`、`:103`、`:121`。
- 证据：当前检查 `_test` 后缀、确认字符串、连接身份和非 superuser，但持久共享数据库只要满足命名规则仍可通过。随机 search_path schema 不能约束未来迁移中的 schema-qualified SQL、extension 或数据库级 DDL。
- 影响：downgrade 可能在持久或共享测试数据库上执行，并可能影响随机 schema 之外的对象。
- 关闭要求：downgrade 只能运行于本次新建的一次性数据库/容器；或至少验证管理员创建的不可伪造 disposal marker、数据库 owner、连接独占性和全局对象策略。迁移脚本还需门禁 schema-qualified/global DDL。
- 状态：OPEN。

### REV01-P2-01：生产数据库与 Redis TLS 策略未收紧

- 来源：Security Review Medium。
- 位置：`apps/api/src/platform_api/settings.py:62`、`:79`、`:211`。
- 证据：staging/production 接受不带强制验证 TLS 参数的 PostgreSQL URL，也接受 `redis://`。
- 影响：在非受控网络部署时，数据库凭据和业务数据可能明文传输。
- 关闭要求：production 默认要求 PostgreSQL `sslmode=verify-full`（或等价验证）及 `rediss://`；私网/service mesh 例外必须由独立显式配置、文档和测试限定，不能隐式降级。
- 状态：OPEN。

### REV01-P2-02：OpenAPI 净化函数污染调用进程状态

- 来源：Bugbot P2；Security Review Low；人工归并为项目 P2。
- 位置：`scripts/export_openapi.py:16`、`:33`。
- 证据：`sanitized_schema()` 覆盖进程环境并清空 Settings cache，但没有在 `finally` 中恢复。它只覆盖当前已知字段，未来新增影响 schema 的变量可能重新引入环境漂移。
- 影响：程序化调用导出函数后，后续代码可能在 `APP_ENV=local`、认证/存储配置为空的状态运行；新增配置字段可能破坏跨环境稳定性。
- 关闭要求：优先把导出限定为显式 allowlist 环境的子进程；若保留程序化 API，必须快照、清空、设置并在 `finally` 中恢复环境和缓存。增加进程内无副作用测试及未知应用变量测试。
- 状态：OPEN。

### REV01-P2-03：base catalog allowlist 未覆盖全部迁移对象类型

- 来源：Bugbot P2。
- 位置：`apps/api/tests/postgresql/catalog.py:9`、`:38`。
- 证据：当前只枚举 tables、indexes、constraints、types、sequences、triggers，未枚举 views/materialized views、functions/procedures、policies、domains、collations、grants 等。
- 影响：迁移残留上述对象时，`downgrade base` 仍可能被误判为清理完整。
- 关闭要求：根据平台允许的迁移对象建立完整 catalog inventory 和显式 base allowlist，至少补齐 views、materialized views、routines、policies、domains 和 grants；新增残留对象的预期红灯测试。
- 状态：OPEN。

### REV01-P2-04：Keycloak issuer 不支持合法 context prefix

- 来源：Bugbot P2。
- 位置：`apps/api/src/platform_api/settings.py:110`。
- 证据：路径被严格限制为恰好 `/realms/<realm>` 两段，`https://id.example.com/auth/realms/platform` 等部署形式会被拒绝。
- 影响：合法 Keycloak 反向代理/上下文路径部署无法通过 staging/production 启动校验。
- 关闭要求：允许非空前缀，但最后两段必须为 `realms/<realm>`；继续禁止凭据、query、fragment 和不安全 scheme，并增加前缀/绕过测试。
- 状态：OPEN。

### REV01-P2-05：OSS public endpoint 尚无运行时 DNS 防护闭环

- 来源：Bugbot P2。
- 位置：`apps/api/src/platform_api/settings.py:57`、`:201`。
- 证据：配置构造期对普通 DNS hostname 只做字面允许；平台尚无 OSS 客户端把 `validate_public_url()` 应用于实际请求。
- 影响：解析到 RFC1918、link-local 或 metadata 网段的普通域名仍可作为 OSS public endpoint 通过部署配置。当前验收只能证明 IP 字面量保护，不能宣称 OSS DNS SSRF 已闭环。
- 关闭要求：在真实 OSS 客户端出站边界执行解析/连接策略，或在客户端实现前收窄验收声明并将运行时门禁作为 OSS 接入的阻断前置条件。
- 状态：OPEN。

## 4. 已确认关闭或未发现回归的范围

- M0R-05R-01 已能拒绝数据库/角色身份不匹配和 superuser，并要求独立 downgrade 确认；静态确认值只应视作防误操作 interlock，不是安全凭据。
- M0R-05R-02 的 SQLSTATE `23505` 与目标约束名断言有效；全部 Alembic heads 的集合比较有效，但 catalog 对象种类仍需扩展。
- M0R-05R-03 的 FastAPI dependency override 确实指向随机 PostgreSQL schema，身份同步、企业/项目生命周期、非成员 404 和回滚证据未发现明确回归。
- M0R-03R-01 已把身份字段检查从全 schema 字符串搜索改为逐 operation 输入语义检查，并正确区分 OpenAPI Bearer 声明与运行时 401/404 证据。
- 本次未发现提交中包含已知真实凭据，也未发现新的租户授权回归。

## 5. 评审质量与限制

- 两个专项代理均报告远端 SSH 超时；主评审已在 `f159390` 上恢复连接并复核全部发布位置，故本报告位置以服务器当前代码为准。
- 本次是本地差异复审，没有远端 PR、CI、镜像摘要、Staging 配置来源或第三方签字证据。
- 未运行攻击性外网测试，也未对真实 DNS rebinding、受控代理或云网络策略进行部署验证。

## 6. 最终裁决

REV-01：`REMEDIATION_REQUIRED`。

在 REV01-P1-01 与 REV01-P1-02 关闭前，禁止进入 M0R-06/M0R-07 或新增 M1 业务能力。全部 P1/P2 关闭并经过测试先行、专项回归后，必须重新执行一次新的 REV-01 Bugbot → Security Review → 人工复核，不得复用本报告直接升级状态。
