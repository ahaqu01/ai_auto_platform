# M0R-04R-05 OSS 运行时范围状态

OSS_RUNTIME_SSRF_STATUS: NOT_IMPLEMENTED_BLOCKING_CLIENT

## 当前事实

平台当前只有 `oss_public_endpoint` / `oss_internal_endpoint` 配置校验，没有 boto3、botocore、aioboto3、MinIO SDK 或自研 OSS HTTP 请求链路。因此目前只能证明：

- 公网 IP 字面量与已知 metadata hostname 的配置期拒绝；
- 可复用 DNS/重定向策略的单元行为；
- JWKS 客户端的固定 peer 运行时闭环。

不能据此声称 OSS 请求已经获得运行时 DNS、重定向或 socket peer 防护。

## 对 M0R-04R-02 的范围修订

M0R-04R-02 验收标准第 4、5 条中的“运行时出站”仅表示可复用策略函数及已接入的 JWKS 客户端，不构成 OSS 客户端运行时证据。其验收记录中的运行时解析/重定向证据同样不得外推到尚不存在的 OSS 请求链路。本文件是该范围的当前修订说明。

## 解除阻断条件

引入任何 OSS SDK 依赖或在生产代码中消费 `oss_public_endpoint` 前，必须在同一任务中：

1. 在真实请求 transport 边界逐跳解析并验证公网地址；
2. TCP 固定到本次验证 IP 并复核实际 socket peer；
3. 保持原 hostname 的 Host、TLS SNI 和证书校验；
4. 每次重定向重新执行上述过程；
5. 增加真实客户端出站测试后，原子更新本状态和架构阻断测试。
