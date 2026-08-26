# REV-01R 双专项复审报告

- 复审日期：2026-08-26
- 复审范围：`rev-01-remediation-required..c1fefb5`
- 被审版本：`c1fefb55865af5da8ba690d59f0e93a7a1cb38b7`
- 评审方式：Bugbot Review + Security Review

## 结论

`REV-01R` 通过。P1 为 0，P2 为 0；原 REV-01 的两个 P1 与五个 P2 均已闭环。新增两个不阻塞的 P3，进入后续维护清单。

## 原问题闭环

- `REV01-P1-01`：已关闭。JWKS 每跳重新解析并固定到已验证地址，校验实际 peer，同时保留原 hostname 的 TLS SNI/Host。
- `REV01-P1-02`：已关闭。迁移 downgrade 使用随机一次性数据库，验证 owner、marker 与独占连接，并独立确认销毁。
- `REV01-P2-01`：已关闭。生产数据库强制 `sslmode=verify-full`，Redis 强制 `rediss://`，私网降级需要显式开关。
- `REV01-P2-02`：已关闭。OpenAPI 在 allowlist 子进程内导出，不污染调用进程环境或 Settings cache。
- `REV01-P2-03`：已关闭。迁移 inventory 覆盖扩展 PostgreSQL catalog 对象，并有逐类残留测试。
- `REV01-P2-04`：已关闭。Keycloak issuer 支持安全 context prefix，并拒绝 userinfo、query、fragment 等绕过。
- `REV01-P2-05`：按范围降级路径关闭。OSS 客户端尚未实现，文档明确阻断状态，架构测试禁止提前接入无固定传输保护的 SDK/端点。

## 新增 P3

1. `apps/api/src/platform_api/common/public_network.py:47`：`validated_public_addresses()` 实际返回 `tuple[str, ...]`，类型标注仍为 `str`。建议后续改正类型标注。
2. `apps/api/tests/postgresql/conftest.py:188-208,233-260`：一次性数据库在创建后、teardown 前才校验 `TEST_DATABASE_ALLOW_DESTROY`。误配置会拒绝 DROP 并留下 orphan 数据库。建议在 `CREATE DATABASE` 前 fail-fast，并保留 teardown 前二次校验。

## 版本管理决定

- 本次复审仅记录结论，不混入 P3 修复。
- 评审记录独立提交并打标签 `rev-01r-reviewed`。
- 两个 P3 后续以独立小提交处理并分别验证。
