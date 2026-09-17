# M2-REVIEW-01 运维公平性验收记录

日期：2026-09-17

## 范围

关闭详细评审中的 P1-BUG-01、P1-BUG-02 的代码缺陷；历史 `m2-accepted` 不移动。

## 实施

- 分支：`codex/m2-review-remediation`。
- 首次实现：`5b99fa6`；失败/重启反证增强：`c728a20`。
- 迁移：`20260916_12`，增加 `artifacts.last_reconciled_at` 与全局维护游标表。
- 对账按最久未尝试顺序轮转；成功或失败的 HEAD 都推进持久化尝试时间。
- 孤儿 key 扫描分批推进并回绕，重启使用数据库中的游标，不再重复占用首批已知 key。
- 内部对账进度更新不增加产品 version；缺失对象状态变更仍增加产品 version 并发出 SYSTEM 事件。

## 验收证据

- Ruff：通过。
- 维护/调度专项：`18 passed`。
- API 全量非 PostgreSQL 回归：`281 passed, 32 deselected`。
- 反证用例：5 条记录、batch size=2，多轮扫描覆盖全部资产；首批持续 HEAD 超时不阻塞尾部缺失资产；前三轮独立 Worker 实例能够到达并清理尾部孤儿。
- CI `35112435751`：`5b99fa6` success。
- CI `35170834811`：`c728a20` success（baseline、PostgreSQL、security）。
- 发布工作树无未提交产品变更；未切换 Demo/Staging 镜像或数据库迁移。

## 裁决

`CODE/CI ACCEPTED`，允许进入 M2-REVIEW-02。真实 MinIO/OSS 多批次复验与受控部署仍必须在 M2-REVIEW-04 完成；本记录不是整个 M2 复评整改最终验收或四方签署。
