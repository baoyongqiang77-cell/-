# 无人机智能巡检系统

本仓库用于“无人机智能巡检系统”的正式研发准备、本地演示、规则级验收和后续版本迭代。

## 文档入口

优先阅读：

1. `AGENTS.md`
2. `docs/README.md`
3. `docs/00-baseline/source-originals/无人机智能巡检系统_架构方案内部开发V2.0.md`
4. `docs/00-baseline/source-originals/无人机智能巡检系统_软件开发功能说明书V2.0.md`
5. `docs/00-baseline/PRD.md`
6. `docs/00-baseline/Architecture.md`
7. `docs/00-baseline/API.md`
8. `docs/00-baseline/Roadmap.md`

## 当前阶段

- M1：平台主链路模拟闭环可展示。
- M2：真实 14 算法、真实 DJI 接入、国产卡实测、生产外部接口仍需后续交付与验收。
- 当前本地 Web Demo 仅用于客户阶段性演示，不代表生产系统已完成。

## 本地测试

```powershell
& 'C:\Users\baoyongqiang\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
```

## 本地 Web Demo

```powershell
& 'C:\Users\baoyongqiang\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\serve_web_demo.py
```

访问：

```text
http://127.0.0.1:8765
```

演示账号说明见：

```text
docs/50-demo/演示环境与账号说明.md
```

## 命令行 MVP 展示

```powershell
& 'C:\Users\baoyongqiang\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\mvp_demo.py
```
