# M0R-03R-01 OpenAPI 身份语义与稳定导出验收标准

- 制定日期：2026-08-24
- 基线提交：`287f2320f6528e5607b875c4cc5a287e70b813ba`
- 基线标签：`m0r-05r-03-implemented`
- 目标状态：`IMPLEMENTED_LOCAL`

## 验收条件

1. 身份输入检查必须逐个 HTTP operation 遍历，覆盖 path/query/header/cookie parameters 与 request body，不得再对整个 OpenAPI JSON 做字符串搜索。
2. request body 检查必须递归处理 properties、items、allOf/anyOf/oneOf 和本地 `$ref`。
3. 禁止调用方声明的身份字段至少包含 `user_id`、`actor_id`、`subject`、`owner_id`；字段名按大小写及连字符/下划线规范化后比较。
4. 响应 schema、数据库模型或描述文本出现身份字段不得误报。
5. 允许按 operation、输入位置和字段名维护显式审批例外；空泛的全局忽略项不允许。
6. 当前受保护 operations 不得包含禁止身份输入，且 operation ID 必须存在并唯一。
7. Bearer OpenAPI 声明只证明契约标注，不得作为运行时授权通过证据；验收记录必须分别引用实际 401 和租户隐藏 404 测试。当前无“资源可见但角色不足”的 API，因此不得虚构 403 证据；未来增加该类 operation 时 403 测试为强制项。
8. OpenAPI 导出进程必须在导入 FastAPI 应用前覆盖所有 schema-generation 相关配置为显式本地安全值，不读取调用者的 production/staging 连接配置来构造 schema。
9. 两个只保留最小进程变量、但注入相互冲突/恶意应用配置的子进程导出结果必须字节相等，并与受控快照一致。
10. 导出时必须执行身份输入策略；违反策略时不得生成新的受控契约。
11. OpenAPI 专项、API 全量、Ruff、快照 check、Web、Agent、Compose 回归通过；独立提交并创建 `m0r-03r-01-implemented` 标签，提交后工作区干净。

## 状态边界

本任务不替代运行时认证授权测试，也不代表 CI/Staging/安全签字完成，只可标记 `IMPLEMENTED_LOCAL`。
