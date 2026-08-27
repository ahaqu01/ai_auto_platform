# Acceptance Status Index

> Owner：QA 负责人
> Updated：2026-08-26
> Status：EVIDENCE INDEX
> Authoritative current status：[../CURRENT_STATUS.md](../CURRENT_STATUS.md)

## 当前里程碑裁决

| Slice | 当前状态 | 说明 |
|---|---|---|
| M0R-03/04/05 及整改包 | `IMPLEMENTED_LOCAL / REVIEWED` | REV-01R P1=0、P2=0；缺少 CI/Staging，不能标记 ACCEPTED |
| REV-01R | `PASSED` | 双专项评审已完成；两个 P3 不阻塞 |
| M0R-06 | IMPLEMENTED_LOCAL | 文档治理验收通过 |
| M0R-07 | IMPLEMENTED_LOCAL | 运行可靠性验收通过 |
| CI/Staging baseline | VERIFIED_STAGING / BLOCKED_EXTERNAL | 服务器验证通过；远端协作门禁待仓库 |
| M1-01 Keycloak IaC | IMPLEMENTED_LOCAL | Realm/Client/Role 与空卷重建验收通过 |
| M1-PRE-01 前置健壮性整改 | IMPLEMENTED_LOCAL | 两个 P3 与 CI/doc checker 健壮性验收通过 |

| M1-02 BFF 会话 | IMPLEMENTED_LOCAL | PKCE、Redis 会话、Cookie/CSRF、退出与管理台验收通过 |
历史验收结果中的“通过”只表示所列测试在当时通过，不自动升级当前里程碑状态。

## 记录规则

1. 记录 Git 提交、迁移版本、环境和精确命令。
2. 本地测试通过最高只能达到 `IMPLEMENTED_LOCAL`。
3. 安全与租户切片需要 PostgreSQL 及真实身份提供方验证。
4. `ACCEPTED` 需要 CI、Staging 和签署证据。
5. 历史记录不回写；状态纠偏写入新记录和 `CURRENT_STATUS.md`。
