# M1-05 企业成员邀请与 RBAC 验收标准

> Owner：平台工程
> 日期：2026-08-27
> 状态：ACCEPTANCE_DEFINED

## 目标与边界

完成企业邀请和 Owner/Admin/Member 权限矩阵。Owner 降级或移除的生产路径属于 M1-06，本阶段必须拒绝该操作，不以非并发安全方式提前实现。

## 验收项

1. Owner/Admin 可创建、查看、撤销邀请；Member 返回 403；非成员保持租户隐藏语义 404。
2. 邀请只允许 ADMIN/MEMBER，明文 token 仅创建响应返回，数据库只保存 SHA-256 摘要。
3. 邀请默认 7 天过期；撤销、过期、已接受 token 不可接受；token 只能成功接受一次。
4. 接受邀请要求当前身份邮箱与受邀邮箱大小写不敏感匹配，否则返回 403。
5. 接受成功原子创建 organization_members，重复成员或重复 token 不产生第二行。
6. 任意企业成员可查看成员列表；非成员返回 404。
7. Owner/Admin 可调整或移除非 Owner 成员；Member 无权操作；Owner 目标在 M1-05 返回 403。
8. 项目创建仅 Owner/Admin 允许，Member 返回 403；成员仍可读取企业项目。
9. 被移除成员立即失去企业成员、邀请、项目等资源访问权。
10. 新表迁移支持 upgrade/downgrade/upgrade，约束、外键和 token 摘要长度在真实 PostgreSQL 验证。
11. OpenAPI 快照、API/PostgreSQL/Web/Go/文档与 Demo 回归通过。
12. 输出开发文档、验收记录、独立提交与 implemented 标签，提交后工作区干净。

## 判定

第 1—10 项任一失败即不通过。外部远端 CI、PR 或 Staging 缺少授权时只标记 BLOCKED_EXTERNAL。
