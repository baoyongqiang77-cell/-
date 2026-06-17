# DJI Dock 3 配套 DJI Cloud API 完整规范（依据大疆官方开发者文档）

## 一、适配 DJI Cloud API 版本

1. **最低兼容基线**：Cloud API V1.14.0（2025-04-15 官方发布，完整支持 DJI Dock3 全部专属能力：自定义禁飞区、远程强制降落、航线空中下发、远程解锁等）DJI
2. **推荐稳定版本**：V1.14.0 ~ V1.14.x 迭代版；不建议低于 V1.13，低版本无 Dock3 专属接口
3. **机场固件配套要求**：DJI Dock3 固件≥14.03.00.03，方可完整对接 V1.14.0 Cloud APIDJI
4. 配套边缘 SDK：Edge SDK V1.2.0（Dock3 本地边缘计算配套）DJI

## 二、App Key / App Secret / 证书（License）规则

### 1. 凭证获取入口（官方渠道唯一）

登录大疆开发者平台 [https://developer.dji.com/cn/](https://link.wtturl.cn/?target=https%3A%2F%2Fdeveloper.dji.com%2Fcn%2F&scene=im&aid=497858&lang=zh) → 开发者中心 → Apps → CREATE APP，**App Type 必须选择 Cloud API**，提交后激活邮件生成全套凭证DJI

### 2. 三类凭证定义与用途

表格

|    凭证     |   名称   |     性质     |                           使用场景                           |
| :---------: | :------: | :----------: | :----------------------------------------------------------: |
|   App Key   | 应用公钥 |   公开标识   |  OAuth 鉴权 client_id、HTTP 请求签名参数、MQTT 设备绑定标识  |
| App Secret  | 应用私钥 |   绝密密钥   |  HmacSHA256 签名加密、禁止前端 / 客户端明文存储，仅后端使用  |
| App License | 应用证书 | 设备校验凭证 | DJI Enterprise App 配置 Dock3 上云、Pilot2 设备校验、机场绑定鉴权核心证书 |

### 3. 核心约束规则

1. 一套 App Key+Secret+License**仅对应 1 个 Cloud API 应用**，不可多项目共用；
2. App Secret 一旦泄露，需在开发者后台重置，重置后全部存量设备 / 接口立即失效；
3. License 分**测试环境 / 生产环境**，不可混用；Dock3 现场配置必须填入对应环境 License；
4. 无独立 SSL 证书下发：MQTT 通信、Webhook 回调统一强制 HTTPS/TLS 加密，由大疆云端标准 CA 证书加密，第三方无需申请专用证书；设备侧 MQTT 强制 TLS 1.2+。

## 三、回调地址（Webhook / 事件通知）强制规则

### 1. 基础协议硬性要求（不可违背）

1. **协议强制 HTTPS**，不支持 HTTP、ws 明文；域名需合法备案，自签证书不兼容，必须公网可信 CA 证书（Let’s Encrypt、商用 SSL）
2. 请求 Method 固定：`POST`，Content-Type：`application/json`
3. 端口：标准 443，自定义端口仅支持 443/8443，其他端口大疆云端无法访问

### 2. 地址格式规范

- 完整示例：`shturl.cc/2DwZ6MeomDIRHOQgbVn2LygxsTpYx`
- 禁止 IP 裸地址（如[https://123.45.67.89/api](https://link.wtturl.cn/?target=https%3A%2F%2F123.45.67.89%2Fapi&scene=im&aid=497858&lang=zh)），必须域名；内网地址、局域网地址无法接收回调
- 路径层级无限制，但需固定接口持续接收全量设备事件（设备上下线、任务完成、媒体上传、故障告警、Dock 舱门 / 充电状态变更）

### 3. 签名校验安全规则（防篡改必实现）

回调请求 Header 携带 4 个校验字段，使用 App Secret 做 HmacSHA256 验签：

- `X-DJI-Timestamp`：毫秒级时间戳，校验时间偏差 ±5 分钟，防止重放攻击
- `X-DJI-Nonce`：随机字符串
- `X-DJI-Signature`：签名结果
- 签名原文拼接规则：`AppKey + X-DJI-Timestamp + X-DJI-Nonce + event_type + sub_type`，使用 App Secret 做 HmacSHA256 输出小写 hex 字符串

### 4. 响应规范

第三方服务收到回调后，**必须在 3 秒内返回 JSON**：

json

```
{"code":0,"message":"success","data":{}}
```

code≠0 或超时无响应时，大疆云端会重试 3 次，间隔 2s；连续失败则暂停推送该 Dock3 设备事件。

### 5. 两类回调区分（Dock3 场景）

1. **全局 Webhook 回调**（开发者平台应用配置）：接收全部绑定 Dock3 的通用事件（设备在线离线、机场状态变更）
2. **媒体文件上传专用回调**（接口单独配置）：航线航拍素材、舱内相机录像上传完成通知，路径格式固定`/media/api/v1/workspaces/{workspace_id}/group-upload-callback`DJI

### 6. 额外约束

- 回调接口不可添加登录拦截、Cookie 鉴权，仅依靠 Header 签名做身份校验；
- 单应用仅支持配置**1 个主回调地址**，如需多业务分流，需第三方后端内部转发；
- Dock3 专属事件类型：`dock_status_report`（机场温感、充电、舱盖）、`dock_remote_control_result`（远程起降 / 迫降结果）、`dock_custom_flyzone_sync`（自定义禁飞区同步）。

## 官方文档参考链接

1. Cloud API 总文档：[https://developer.dji.com/doc/cloud-api-tutorial/cn/overview/](https://link.wtturl.cn/?target=https%3A%2F%2Fdeveloper.dji.com%2Fdoc%2Fcloud-api-tutorial%2Fcn%2Foverview%2F&scene=im&aid=497858&lang=zh)
2. Dock3 机场专属能力：[https://developer.dji.com/doc/cloud-api-tutorial/cn/feature-set/dock-feature-set/](https://link.wtturl.cn/?target=https%3A%2F%2Fdeveloper.dji.com%2Fdoc%2Fcloud-api-tutorial%2Fcn%2Ffeature-set%2Fdock-feature-set%2F&scene=im&aid=497858&lang=zh)
3. 鉴权与 Webhook 签名规范：[https://developer.dji.com/doc/cloud-api-tutorial/cn/overview/authentication/](https://link.wtturl.cn/?target=https%3A%2F%2Fdeveloper.dji.com%2Fdoc%2Fcloud-api-tutorial%2Fcn%2Foverview%2Fauthentication%2F&scene=im&aid=497858&lang=zh)