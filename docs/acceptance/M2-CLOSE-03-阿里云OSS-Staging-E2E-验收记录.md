# M2-CLOSE-03 阿里云 OSS Staging E2E 验收记录

- 日期：2026-09-16
- 环境：`aiautoplatform`，华东 1（杭州），Staging `:8081`
- 结论：**通过（经批准的范围变更）**

## 已通过

- Bucket ACL 私有；阻止公共访问已开启。
- CORS 两个精确 Staging 来源生效；OPTIONS 返回 200；GET/PUT/HEAD、ETag、600 秒缓存符合标准。
- Playwright 真实 OSS 用例通过，耗时 4.0 分钟。
- 100 MiB 暂停/恢复完成；取消任务 ABORTED。
- 1 KiB 首次 PUT 断线后重试完成。
- 1 GiB Multipart 上传完成。
- 资产状态 AVAILABLE/VERIFIED；授权下载 SHA-256 与源内容一致。
- 测试结束 Bucket 对象数为 0。
- RAM 管理越权探测返回 403 NoPermission。
- 新 RAM AccessKey（尾号 `8cg4`）已注入 Staging，配置文件权限为 `0600`，API 重建后健康状态为 `healthy`。
- 使用新 Key 重新执行完整 Playwright 用例：`1 passed (4.0m)`；清理后 Bucket 对象数再次确认为 0。
- 本平台已不再使用旧 Key。
- 项目目录与受限配置目录中的旧 Key 引用数为 0。
- 携带 OSS 配置的 Staging API、PostgreSQL、Keycloak、MinIO 容器均使用新 Key；六个 Staging 服务全部健康，Web HTTP 为 200。
- Demo 环境继续使用隔离的本地 MinIO 凭据，不属于阿里云旧 Key 使用。

## 范围变更与风险接受

- 项目负责人于 2026-09-16 明确确认：关闭 M2-CLOSE-03 并启动 M2-CLOSE-04；其他服务继续使用的旧 Key 作为本项目范围外遗留风险管理。
- 本项目文件旧 Key 引用为 0，全部项目 OSS 服务已使用新 Key，补偿控制和真实 OSS E2E 均通过。
- 旧 Key 仍应按已暴露凭据处理；其外部依赖迁移、停用和删除责任不因本次范围变更消失。

## 最终判定

M2-CLOSE-03 在批准的范围变更下满足本项目关闭条件，状态为 `ACCEPTED`。允许启动 M2-CLOSE-04；本判定不等同于 M2 阶段总签。
