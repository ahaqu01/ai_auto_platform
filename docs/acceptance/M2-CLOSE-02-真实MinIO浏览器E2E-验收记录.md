# M2-CLOSE-02 真实 MinIO 浏览器 E2E 验收记录

> 日期：2026-09-15  
> 环境：http://192.168.1.129:8080  
> 分支：`codex/m2-assets-storage`  
> 结论：ACCEPTED

## 1. 验收对象

实现提交：`34ead76`、`b3d03ba`、`d466b49`。验收对象包含资产列表/详情/下载界面、LAN HTTP 请求 ID 兼容、当前组织一致性、Keycloak 临时用户夹具及真实 MinIO Playwright runner。

## 2. 执行与结果

### 2.1 静态与单元门禁

- `git diff --check`：通过。
- `npm --prefix apps/web test -- --run`：7 个测试文件、18 项测试全部通过。
- `npm --prefix apps/web run build`：`vue-tsc -b` 与 Vite 生产构建通过。
- `bash -n scripts/run_m2_close02_e2e.sh scripts/manage_demo_e2e_user.sh`：通过。
- GitHub Actions run `34970847263`（提交 `d466b49`）：`success`。

### 2.2 环境门禁

- Demo 数据库由 `20260827_07` 升级到 `20260915_11`。
- Web、API、PostgreSQL、Redis、MinIO、Keycloak：全部 healthy。

### 2.3 真实浏览器矩阵

执行：

```bash
E2E_PASSWORD='<ephemeral>' E2E_RUN_ID=20260915matrix4 \
  bash scripts/run_m2_close02_e2e.sh
```

最终结果：1 个组合场景通过，耗时约 1.5 分钟。

- 中文 Keycloak 登录：通过。
- UI 创建组织和项目：通过。
- 当前组织跨页面一致：通过。
- 100 MB 限速上传暂停/恢复：通过。
- 9 MB 上传取消：通过。
- 1 KB 首个 PUT 注入失败后自动重试：通过。
- 1 GB Multipart 上传及服务端强校验：通过。
- 资产列表与详情：`AVAILABLE/VERIFIED`，通过。
- 10 分钟授权 URL 真实下载：文件名及数据流有效，通过。

### 2.4 清理核验

runner 输出显示 3 个完成对象均删除、临时组织删除 1 条、一次性 Keycloak 用户不存在。随后复核：

- `organizations`：0 条测试残留。
- `artifacts`：0 条测试残留。
- `upload_sessions`：0 条测试残留。
- Demo MinIO：0 个测试对象残留。

## 3. 验收过程中发现并关闭的问题

1. `crypto.randomUUID` 在可信局域网 HTTP 页面不可用：已增加 UUID v4 形态请求 ID 回退及单测。
2. Demo 健康但数据库仍为 M1 schema：已重建 migrate/API 并升级到当前 head。
3. 资产页未沿用当前组织：已修复并增加浏览器断言。
4. Keycloak 邮箱用户名模式导致夹具设置密码失败：已按邮箱回查并使用用户 ID 操作。

## 4. 审计与安全说明

- E2E 密码仅以运行时环境变量注入，未写入仓库。
- 测试只使用 Demo MinIO 本地凭据，不使用此前暴露的阿里云长期 AccessKey。
- 预签名 URL 只保存在上传控制器内存，未进入 localStorage、页面文本和验收日志。
- 清理以精确测试组织和数据库记录的对象 Key 为边界，不触碰非测试数据。

## 5. 结论与剩余项

M2-CLOSE-02 满足全部验收标准，状态为 ACCEPTED。它关闭的是 Demo/MinIO 真实浏览器闭环；阿里云 OSS Staging 真实 E2E、凭据轮换证明和 Bucket CORS 仍属于 M2-CLOSE-03，M2 总签及 `m2-accepted` 标签仍不得提前创建。
