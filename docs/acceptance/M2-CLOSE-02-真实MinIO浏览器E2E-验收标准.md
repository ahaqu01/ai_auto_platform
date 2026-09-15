# M2-CLOSE-02 真实 MinIO 浏览器 E2E 验收标准

> 日期：2026-09-15  
> 适用环境：Demo（真实 Chromium + Keycloak + BFF + API + PostgreSQL + MinIO）

## 一、强制门禁

1. Demo Web、API、PostgreSQL、Redis、MinIO、Keycloak 全部 healthy。
2. Demo 数据库 Alembic 版本为当前 head `20260915_11`。
3. 登录页中文标题可见；认证完成后使用 HttpOnly BFF Session 访问受保护 API。
4. 通过界面创建临时组织和项目，资产页必须沿用当前组织。
5. 100 MB 文件在真实 MinIO PUT 过程中可暂停，并从已登记分片恢复至完成。
6. 上传中的 9 MB 文件可取消，服务端会话进入终止状态，不生成可用资产。
7. 1 KB 文件首次 PUT 故障后自动重试并完成，至少观察到两次 PUT 尝试。
8. 1 GB 文件完成真实 Multipart 上传；服务端强校验通过并形成 `AVAILABLE/VERIFIED` 资产。
9. 上传完成后资产列表可见；详情返回完整性、扫描状态和 SHA-256。
10. `AVAILABLE` 资产经授权端点生成短期 URL，Chromium 完成真实下载，文件名和数据流有效。
11. 预签名 URL、对象存储凭据和一次性测试密码不得进入代码、页面持久化或验收文档。
12. runner 在成功或失败时均清理临时 Keycloak 用户、组织/项目/会话/资产和 MinIO 对象。
13. Web 单元测试、TypeScript 检查、生产构建及 GitHub Actions 全部通过。

## 二、失败判定

任一强制门禁未满足即不得标记 M2-CLOSE-02 ACCEPTED。仅 Mock 测试通过、仅 API 直调通过、保留临时业务数据或用长期 OSS 凭据替代 MinIO 均不算通过。

## 三、退出条件

- 实现、矩阵增强、中文认证断言均形成独立 Git 提交。
- 同名开发文档和验收记录进入仓库。
- 验收记录包含运行命令、样本规模、最终结果、清理核验及已知剩余边界。
