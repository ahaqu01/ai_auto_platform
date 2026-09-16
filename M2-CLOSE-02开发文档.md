# M2-CLOSE-02 开发文档

> 工作包：真实 MinIO 浏览器端到端闭环  
> 日期：2026-09-15  
> 分支：`codex/m2-assets-storage`  
> 实现提交：`34ead76`、`b3d03ba`、`d466b49`

## 1. 目标与边界

本工作包把 M2-08 的 Mock Web 测试提升为真实 Demo 全栈验收。浏览器请求必须经过中文 Keycloak、BFF Cookie、FastAPI、PostgreSQL、预签名 URL 和 MinIO；不使用假的对象存储响应。本工作包不接入阿里云 OSS，OSS Staging 证据归 M2-CLOSE-03。

## 2. 完成内容

### 2.1 资产可见与下载闭环

- 数据资产页新增项目资产列表、状态、大小和完整性摘要。
- 新增资产详情，展示完整性、安全扫描及 SHA-256。
- 仅对 `AVAILABLE` 资产启用下载，经授权 API 获取 10 分钟预签名 URL。
- 上传完成后自动刷新资产列表；切换组织/项目时同步刷新。
- 资产页沿用“组织与项目”页保存的当前组织，避免上传落入同一用户的错误组织。

### 2.2 可信局域网 HTTP 兼容

浏览器在 `http://192.168.1.129:8080` 这类非安全上下文中不保证提供 `crypto.randomUUID`。请求幂等键改为：优先使用原生 `randomUUID`，不可用时生成符合 UUID v4 形态的非安全随机请求 ID。该值只用于请求去重，不承担密钥或令牌职责。

### 2.3 可重复真实 E2E

- 新增 `apps/web/e2e/m2-close-02-minio.spec.ts`。
- 新增 `scripts/run_m2_close02_e2e.sh` 一键入口。
- 样本矩阵：1 KB、100 MB、1 GB。
- 100 MB 验证限速条件下暂停和恢复；9 MB 验证取消。
- 1 KB 首个 MinIO PUT 被主动中断，验证客户端自动重试。
- 1 GB 验证完整 Multipart、服务端 SHA-256 校验、列表可见。
- 真实下载校验浏览器收到的文件名及数据流。
- 中文登录标题作为显式断言。
- runner 使用临时 Keycloak 用户、组织、项目和对象；无论成功失败均以 trap 清理。

### 2.4 测试夹具修复

Demo Realm 开启“邮箱作为用户名”。原脚本创建用户后仍按传入用户名设置密码，首次真实运行暴露失败。现改为用户名未命中时按邮箱回查，并使用 Keycloak 用户 ID 设置密码；删除路径同样支持邮箱回查。

### 2.5 Demo 环境迁移

真实运行发现 Demo 数据库停留在 `20260827_07`，健康检查无法发现 M2 表缺失。已重建 migrate/API 镜像并执行升级，当前 Alembic head 为 `20260915_11`，`upload_sessions` 与 `artifacts` 已可用。

## 3. 运行方式

在项目根目录设置一次性密码后运行：

```bash
E2E_PASSWORD='<ephemeral-password>' E2E_RUN_ID='<unique-run-id>' \
  bash scripts/run_m2_close02_e2e.sh
```

密码不写入仓库、日志或验收文档。runner 完成后删除 Keycloak 用户、测试组织及其级联数据，并按数据库中的精确对象 Key 删除 MinIO 对象。

## 4. 版本记录

- `34ead76 test(storage): add real MinIO browser acceptance`
- `b3d03ba test(storage): cover MinIO size matrix`
- `d466b49 test(auth): assert Chinese login in browser acceptance`

## 5. 结论

M2-CLOSE-02 的真实 MinIO 浏览器闭环已完成并通过验收。真实运行发现并修复了 Mock 无法覆盖的三个问题：LAN HTTP 请求 ID、Demo M2 数据库迁移、当前组织选择一致性。阿里云 OSS 真实凭据、Bucket CORS 与公网/专网链路仍由 M2-CLOSE-03 验证。
