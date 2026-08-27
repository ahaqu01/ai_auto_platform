# Current Status

> Owner：平台工程
> Updated：2026-08-27
> Git baseline：M1-05 提交（标签 m1-05-membership-rbac-implemented）
> Database migration：20260827_04 (head)
> Status：M1-05 IMPLEMENTED_LOCAL / PASSED_LOCAL / BLOCKED_EXTERNAL

## 当前结论

- M1-05 已完成邀请生命周期、Owner/Admin/Member RBAC、成员管理与项目创建授权。
- 邀请仅存 token 摘要，支持单次接受、7 天过期、撤销和重发。
- 被移除成员立即失去访问；Owner 变更留给 M1-06 并发安全路径。
- CI baseline、真实 PostgreSQL和 Demo 验收通过。

## 状态边界

本地与 Demo 证据完整；私有远端、PR、远端 CI 和外部 Staging 签章缺授权，因此不标记 ACCEPTED。

## 权威执行顺序

1. 执行 M1-06 最后 Owner 并发保护。
2. 按 M1-07 至 M1-10 推进。
3. 进入资产/任务域前强制完成 M1-08 和 M1-09。

文档索引见 [文档治理入口](README.md)，验收证据见 [acceptance](acceptance/README.md)。
