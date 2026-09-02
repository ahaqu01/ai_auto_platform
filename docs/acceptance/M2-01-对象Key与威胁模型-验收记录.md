# M2-01 对象 Key 与威胁模型验收记录

- 状态：ACCEPTED
- 日期：2026-09-02
- 分支：`codex/m2-assets-storage`
- 基线：`3a23227`
- 设计提交：`e69b2495530d0ba872244b692aca17fd79ee7ee2`

## 验收结果

| 检查项 | 结果 | 证据 |
|---|---|---|
| 双状态机 | PASS | ADR-0006、设计基线第 2 节 |
| opaque 服务端 Key | PASS | ADR-0006 对象身份决策 |
| 大小/摘要/内容边界 | PASS | ADR-0006、设计基线第 2/7 节 |
| 授权与归档语义 | PASS | ADR-0005/0006、API 草案 |
| 威胁模型 | PASS | 设计基线第 4 节 |
| 失败恢复 | PASS | 设计基线第 5 节 |
| MinIO/OSS 分离 | PASS | 设计基线第 6 节 |
| 凭据治理 | PASS | 交付物不含 AccessKey/Secret；长期凭据不作为应用契约 |
| 实现边界 | PASS | 无上传 API、迁移或 SDK 代码 |
| 文档检查 | PASS | `DOC CHECK PASSED` |
| 完整 CI | PASS | GitHub Actions run `33580267593` |

## 设计裁决

M2-01 采用双状态机、opaque Key、完整服务端 SHA-256、显式安全扫描策略、20 GiB 产品上限和 1 GiB 数据面样本。旧文档中的可读租户路径 Key、抽样摘要和单状态机解释被本设计基线替代。

OSS Staging 的 region、endpoint 和 bucket 已知；长期凭据已明文暴露，必须轮换后再用于后续联调。M2-01 不使用或保存该凭据。

## 结论

设计内容满足 M2-01 强制标准，文档检查和完整 CI 均成功。M2-01 状态为 `ACCEPTED`，允许进入 M2-02。

## 发布证据

设计提交 `e69b249` 的 GitHub Actions run `33580267593` 为 `success`。本证据使用追加提交记录，不改写已推送历史。
