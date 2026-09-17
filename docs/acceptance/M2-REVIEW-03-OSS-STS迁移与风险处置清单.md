# M2-REVIEW-03 OSS STS 迁移与风险处置清单

日期：2026-09-17；问题：P2-SEC-02；状态：`OPEN / CLOUD PREREQUISITES REQUIRED`。

## 2026-09-17 继续执行核查

- 远程整改分支基线为 `182b48bc98ac20f8267cfdb6b7aa8962afd69cd2`，核查时工作树干净；该提交 CI `35180416354` 为 `completed / success`。
- 实际运行容器数据库身份核查再次通过：API 与维护身份均受限、提权拒绝、环境隔离通过；此结果不替代 OSS STS 验收。
- 浏览器清单最初没有标签；打开 RAM 控制台超时后重新枚举，实际出现“阿里云登录页”。绑定该标签再次超时，未取得已登录 RAM 会话，未创建角色或修改权限。
- 已重新读取 Gateway/Runtime：签名使用初始化时的固定 Credentials，Runtime 缓存不会自动刷新临时凭据。不能通过填写一次性 Token 关闭本安全项。
- 实际 API/维护容器仅输出配置存在性布尔值：`OSS_SESSION_TOKEN`、`OSS_ROLE_ARN`、`OSS_CREDENTIALS_FILE`、`OSS_STS_ENDPOINT` 全部为 false；未输出任何凭据值。外部 env 文本的空引号不能当作已配置 Token。
- 本轮未修改运行凭据、未删除其他服务 Key、未启动总签或改动 main/验收标签。下一步需云管理员提供平台专用 Role ARN、可信签发接入方式；不要通过对话发送密钥。若由本代理协助云配置，需先在可控浏览器完成登录。

当前 Staging 在权限 0600 的外部配置中使用项目新长期 RAM Key。数据库拆分未改变 OSS 身份；本轮真实 OSS 产品验收也不是 STS 切换验收。未批准任何长期凭据风险豁免，不删除其他服务使用的旧 Key。

## 缺少的输入

1. 平台专用 RAM Role ARN 和精确可信签发主体，及其 sts:AssumeRole 权限。
2. 内网主机采用何种可信签发方式：独立 STS 签发服务、经批准的 OIDC 联邦身份，或部署到有 RAM 实例角色的 ECS。不能将内网普通主机描述为 ECS，也不直接将签发者长期 Key 注入 API/维护容器。
3. 凭据刷新、监控和泄露响应的运维负责人；任何限期风险处置都需要项目负责人明确批准。

AssumeRole 必须指定 RoleArn，调用者需要角色扮演权限；STS 结果包括临时 Key、SecurityToken 和 Expiration。[阿里云 AssumeRole 文档](https://help.aliyun.com/zh/ram/developer-reference/api-sts-2015-04-01-assumerole)、[STS 访问 OSS](https://help.aliyun.com/zh/oss/developer-reference/use-temporary-access-credentials-provided-by-sts-to-access-oss)。

## 最小权限模板

仓库 `deploy/aliyun/oss-runtime-policy.example.json`：平台角色仅操作 `aiautoplatform/v1/o/*` 的 GetObject/PutObject/DeleteObject/AbortMultipartUpload；ListObjects 限定 bucket 并要求平台前缀。不赋予 RAM 管理、Bucket ACL/CORS 管理、全 Bucket 通配或 ListBuckets。

`deploy/aliyun/sts-issuer-policy.example.json`：签发主体仅能 AssumeRole 指定平台角色；其中 account-id 和 role 是待替换占位符，未创建、未应用。角色信任策略必须精确绑定实际签发主体，不使用任意 RAM 用户或任意联邦来源。授权策略存在叠加效应，必须审查角色已有全部策略和 Bucket Policy，不能只看新模板。[OSS RAM Policy 前缀限制](https://help.aliyun.com/zh/oss/user-guide/access-control-base-on-ram-policy)、[Multipart 权限](https://help.aliyun.com/zh/oss/user-guide/multipart-upload/)。

## 实施与验收顺序

1. 云管理员创建专用角色、精确可信关系、最小 OSS 策略和签发者 AssumeRole 策略，提供非秘密的 ARN 和接入方式。
2. 在隔离环境实现/验证凭据 provider：刷新在到期前完成、并发刷新收敛、过期/刷新失败关闭请求、无长期 Key 回退、签名有效期不超过临时凭据剩余寿命。现有 `OSS_SESSION_TOKEN` 只能注入一次性静态 Token，Settings/Gateway 缓存不自动刷新，不能据此宣称可持续 STS 服务已经实现。
3. Staging API/维护仅持有短期凭据，不携带签发者长期 Key；以实际容器环境键和签发审计证明，而非打印真实值。管理员源配置和历史备份仍可能含长期凭据，需受限保管并按批准流程清理。
4. 真实 STS 下重复上传、完成/重放、HEAD/流式校验、列举、下载、删除、取消及维护；跨前缀、其他 bucket、ACL/RAM 管理负向测试必须拒绝。
5. 跨过至少一次实际凭据到期/刷新周期，证明新凭据继续可用、旧临时凭据失效；模拟刷新故障，不泄露 Token、签名 URL 或 Key。
6. 保存仅含会话时间、状态和脱敏身份的轮换记录，确认测试资源清理。完成后才由项目负责人批准撤销本项目旧运行凭据的 OSS 直接权限；其他服务的旧 Key 不在本轮删除范围。

## 待批准的临时处置

负责人：待指定；建议截止：2026-09-24（尚未批准，不是已生效承诺）。若接入暂时无法完成，只能由项目负责人明确批准受控 Staging 的限期风险处置，并指定负责人、期限、告警和泄露响应；批准前本 P2 安全项保持 OPEN，M2 复评总签不得自动通过。

当前控制：平台使用项目新 Key，外部配置目录/文件限制权限，签名库敏感 debug 被抑制，Bucket 私有且阻止公共访问的历史验收事实不代替本轮权限审查。未输出已发生的新 Key 轮转或已应用 STS 策略记录。
