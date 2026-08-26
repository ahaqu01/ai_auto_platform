# 文档治理索引

> Owner：平台架构负责人
> 版本：1.0
> 状态：CURRENT
> 更新日期：2026-08-26
> 唯一当前状态源：[CURRENT_STATUS.md](CURRENT_STATUS.md)

## 状态定义

- `CURRENT`：当前有效，应作为实施或决策依据。
- `EVIDENCE`：历史执行证据，不代表当前里程碑状态。
- `SUPERSEDED`：已被后续文档替代，仅供追溯。
- `DRAFT`：尚未批准，不能作为门禁依据。

## Owner 与权威范围

| 文档组 | Owner | 状态 | 权威范围 |
|---|---|---|---|
| `CURRENT_STATUS.md` | 交付负责人 | CURRENT | HEAD、里程碑状态、阻塞项和下一步 |
| `design/`、`adr/` | 平台架构负责人 | CURRENT | 产品、架构、数据模型、阶段任务与决策基线 |
| `plans/` | 交付负责人 | CURRENT / SUPERSEDED | 执行顺序与门禁；按替代关系判断 |
| `acceptance/` | QA 负责人 | EVIDENCE | 验收标准与执行证据 |
| `reviews/` | 独立评审人 | EVIDENCE | 评审发现、裁决和复审结论 |
| 根目录交接文档 | 交付负责人 | EVIDENCE | 时间点快照，不替代当前状态源 |

## 计划替代关系

1. `里程碑后开发评审与验收计划.md` 是长期门禁基线。
2. V2.1 曾增量调整 M0-R 顺序；未被后续覆盖的规则继续有效。
3. V3.0 替代 V2.1 中直接进入 M0R-06 的顺序，现已执行完成。
4. V4.0 替代 V3.0 的未关闭整改顺序；随 REV-01R 通过已执行完成。
5. 当前恢复长期计划：M0R-06 → M0R-07 → CI/Staging → 业务开发。

发生冲突时采用：`CURRENT_STATUS.md` → 最新适用计划 → 设计基线 → 历史证据。

## 维护规则

1. 每个工作包完成时同步 `CURRENT_STATUS.md`。
2. 验收记录包含提交、环境、命令和结论。
3. 新计划必须声明替代范围。
4. 历史证据不回写；通过新记录纠偏。
5. 本地测试通过最高只能标记 `IMPLEMENTED_LOCAL`；`ACCEPTED` 需要 CI、Staging 和签署证据。
