# Current Status

> Owner：交付负责人 / 技术 / 安全 / QA
> Updated：2026-08-27
> Git baseline：M1 总体验收审计，标签 `m1-total-acceptance-audited`
> Database migration：`20260827_07` (head)
> Status：M1 NOT ACCEPTED / TESTS_FAILED / BLOCKED_EXTERNAL

## 当前事实

- M1-PRE-01、M1-01 至 M1-10 均已完成本地实现和工作包级验收。
- 全量 API/PostgreSQL `193 passed`，Web `9 passed`，Keycloak service token→受保护 API、Demo 和跨租户证据通过。
- 后端 branch coverage 为 75%，低于总体 80% 门槛，关键 auth/authorization/tenant 未达 90%。
- Realm 无测试用户，真实用户浏览器 BFF E2E 无法执行。
- Python/Go SCA/SAST、当前 M1 远程 CI/外部 Staging 矩阵和四方签字缺失。

## 决策

不得创建 `m1-accepted`，不得进入 M2。详细证据与整改顺序见仓库根目录 `M1总体验收报告.md`。

## 权威执行顺序

1. M1-AC-01 覆盖率补强。
2. M1-AC-02 可重复测试用户与真实浏览器 E2E。
3. M1-AC-03 Python/Go SCA/SAST。
4. M1-AC-04 远程 CI 与外部 Staging 全矩阵。
5. M1-AC-05 四方签字并重新执行总体验收。

文档入口见 [文档治理索引](README.md)，验证证据见 [acceptance](acceptance/README.md)。
