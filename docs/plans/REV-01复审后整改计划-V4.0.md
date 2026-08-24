# REV-01 复审后整改计划 V4.0

- 制定日期：2026-08-24
- 依据：`REV-01-整改双专项复审报告.md`
- 当前基线：`f159390011036abdb9eefeb63b2fca5c264b8791`
- 当前状态：REV-01 `REMEDIATION_REQUIRED`

## 1. 执行原则

1. P1 优先，P1 未清零时暂停文档治理、进程托管和 M1 业务开发。
2. 每个修复包继续执行：验收标准 → 预期红灯 → 实现 → 专项/全量回归 → 独立提交与标签。
3. 安全边界必须由实际连接、数据库生命周期或客户端出站测试证明，不能只依赖字符串/命名约定。
4. 每个发现必须在验收记录中引用发现编号、关闭提交和测试证据。
5. REV-01 只能在全部 P1/P2 修复后重新运行，不能通过修改本次裁决文案来关闭。

## 2. 修订后的执行顺序

### 1. M0R-04R-03：JWKS 连接地址固定（阻断 P1）

- 关闭：REV01-P1-01。
- 验收重点：测试先取得“校验公网、连接切换私网”的 rebinding 红灯；实际 socket peer 必须属于本次验证集合；TLS SNI/hostname verification 保持；每次重定向重新固定地址。
- 标签建议：`m0r-04r-03-implemented`。

### 2. M0R-05R-04：一次性 downgrade 数据库（阻断 P1）

- 关闭：REV01-P1-02。
- 验收重点：每次 downgrade 新建独立数据库或容器；验证 owner、非共享连接和 disposal marker；迁移脚本拒绝未经审批的 schema-qualified/global DDL；销毁目标二次确认。
- 标签建议：`m0r-05r-04-implemented`。

### 3. M0R-04R-04：生产 TLS 与 Keycloak 前缀兼容

- 关闭：REV01-P2-01、REV01-P2-04。
- 验收重点：production PostgreSQL verified TLS、Redis TLS；显式私网例外；Keycloak 最后两段为 `realms/<realm>` 并允许安全前缀；反例不得绕过 query/fragment/userinfo 检查。
- 标签建议：`m0r-04r-04-implemented`。

### 4. M0R-03R-02：无副作用 OpenAPI 导出

- 关闭：REV01-P2-02。
- 验收重点：程序化调用前后环境和 Settings cache 等价；未知应用变量不能影响字节；异常路径同样恢复；导出仍执行身份输入策略。
- 标签建议：`m0r-03r-02-implemented`。

### 5. M0R-05R-05：完整 PostgreSQL base inventory

- 关闭：REV01-P2-03。
- 验收重点：增加 view、materialized view、routine、policy、domain、collation、grant 等清单；逐类注入残留对象获得红灯；base allowlist 完全相等。
- 标签建议：`m0r-05r-05-implemented`。

### 6. M0R-04R-05：OSS 出站策略闭环或范围降级

- 关闭：REV01-P2-05。
- 验收重点：若 OSS 客户端已进入实现范围，真实出站前验证 DNS/重定向/连接 peer；若客户端尚未实现，则更正 M0R-04R-02 验收声明并建立 OSS 客户端接入阻断测试，不得声称运行时 SSRF 已关闭。
- 标签建议：`m0r-04r-05-implemented`。

### 7. REV-01R：整改双专项复审重跑

- 前置：上述 1-6 全部完成。
- 顺序：Bugbot → Security Review → 非作者人工复核。
- 门禁：P1=0、P2=0；所有发现有关闭提交和测试映射；工作区干净。
- 通过后才恢复原计划中的 M0R-06、M0R-07 和后续 CI/Staging 工作。

## 3. 暂停事项

- M0R-06 文档治理；
- M0R-07 API 进程托管；
- M1 身份、租户及业务能力扩展；
- 将任何整改包标记为 `REVIEWED` 或更高状态；
- 在非一次性数据库上执行 migration downgrade。

## 4. 版本管理要求

- 每个包从上一个干净标签开始，禁止把多个发现混成一个不可审查提交。
- 提交前执行 staged diff、敏感信息扫描和 `git diff --check`。
- 标签只标识 `IMPLEMENTED_LOCAL`；REV-01R 通过前不得创建带 `reviewed`、`accepted` 含义的标签。
- 本次 REV-01 文档提交使用失败态标签，不暗示通过。
