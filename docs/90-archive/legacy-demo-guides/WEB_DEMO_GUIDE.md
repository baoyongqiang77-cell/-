# 本地 Web Demo 说明

## 1. 当前口径

本地 Web Demo 用于客户阶段性演示账号和流程，不是生产系统。页面展示的是模拟演示数据，重点覆盖：

- 平台方与客户租户登录。
- 角色菜单差异。
- 客户租户默认无训练、模型发布、平台运维能力。
- M1 主链路模拟闭环。
- 14 算法交付跟踪状态。
- 候选硬件池边界。
- 测试报告入口。

不能承诺：

- 真实 DJI 飞控已接入。
- 真实 14 算法模型已交付。
- 国产卡已最终锁定或完成实测。
- 生产统一身份、数据库、对象存储、消息队列和外部系统已接入。

## 2. 启动方式

### 方式 A：直接打开 HTML

打开：

```text
D:\无人机智能巡检系统\web-demo\index.html
```

### 方式 B：本地 HTTP 服务

在项目根目录执行：

```powershell
cd 'D:\无人机智能巡检系统'
& 'C:\Users\baoyongqiang\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\serve_web_demo.py
```

浏览器访问：

```text
http://127.0.0.1:8765
```

## 3. 演示账号

所有账号密码相同：

```text
Demo@2026
```

| 账号 | 角色 | 演示重点 |
| --- | --- | --- |
| `platform_admin` | 平台管理员 | 总览、训练发布、14 算法、测试报告、平台方全功能口径 |
| `customer_flight` | 客户飞控用户 | 飞控任务、遥测、媒体同步、M1 模拟链路 |
| `customer_viewer` | 客户分析查看员 | 分析事件、告警、工单 |
| `customer_annotator` | 客户标注用户 | 标注任务、数据集状态、客户租户授权样本 |

## 4. 建议演示顺序

1. 使用 `platform_admin` 登录，展示 U0-U7 总览和测试 `30/30 PASS`。
2. 切到“训练发布”，说明平台方可见，但模型发布仍受真实算法和双硬件证据阻断。
3. 切到“14 算法”，说明当前是交付跟踪状态，真实模型未全部闭合。
4. 退出，使用 `customer_flight` 登录，展示客户飞控任务和 M1 模拟闭环。
5. 使用 `customer_viewer` 登录，展示分析事件、人工复核和工单。
6. 使用 `customer_annotator` 登录，展示标注任务和 `FROZEN` 数据集状态。
7. 用客户账号点“训练发布”，展示 `FEATURE_403` 权限边界。

## 5. 关键文件

- `web-demo/index.html`
- `web-demo/app.js`
- `web-demo/styles.css`
- `web-demo/demo-data.js`
- `scripts/serve_web_demo.py`
- `tests/test_web_demo.py`
