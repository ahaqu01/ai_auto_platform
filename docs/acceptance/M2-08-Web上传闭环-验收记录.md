# M2-08 Web 上传闭环验收记录

> 日期：2026-09-15  
> 结论：CODE/CI ACCEPTED；REAL STORAGE STAGING E2E PENDING

## 版本证据

- 分支：`codex/m2-assets-storage`
- 实现提交：`faf08b4`
- 数据库迁移：无新增，head `20260915_11`
- 实现 CI：GitHub Actions run `34928585776`，结论 `success`（baseline、postgresql、security 全部成功）

## 已通过证据

- Web：7 个测试文件、17 项测试全部通过。
- TypeScript：`vue-tsc -b` 通过。
- 生产构建：Vite 构建通过，生成独立 AssetsView chunk。
- 全仓基线：`bash scripts/ci.sh` 通过。
- 覆盖场景：标准和跨 4 MiB 分块 SHA-256、多分片及有序完成、暂停/恢复、服务端分片重读、失败重新签名和三次上限、取消、活动项目过滤、空文件拦截、签名 URL 不进入控制器序列化状态。

## 安全检查

通用敏感字段扫描无命中；真实 OSS 凭据未发送到开发主机扫描命令、未进入源码、文档、构建参数或测试数据。外部 PUT 不携带浏览器凭据。

## 未通过/未执行证据

真实 MinIO/阿里云 OSS 浏览器 E2E、1 KB/100 MB/1 GB 样本、真实 CORS/ETag 暴露尚未执行。因此本记录只签署 M2-08 代码与 CI，不签署 M2 总体验收，不创建 `m2-accepted` 标签。