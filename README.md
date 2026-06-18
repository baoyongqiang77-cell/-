# 无人机智能巡检系统

本仓库用于“无人机智能巡检系统”的正式研发、自动化测试、阶段演示和后续版本迭代。开发前请先阅读 `AGENTS.md`、`docs/README.md` 及 `docs/00-baseline/` 下的基线文档。

## 当前阶段

- M1：建设平台主链路模拟闭环。
- M2：真实 14 算法、真实 DJI 接入、国产卡实测和生产外部接口仍待后续交付验收。
- 演示 Token、SQLite、本地 Web Demo 和 PostgreSQL 冒烟容器均为非生产设施。

## U0 本地环境

在仓库根目录执行：

```powershell
& 'C:\Users\baoyongqiang\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r apps\api\requirements.txt
```

创建数据库表并显式初始化演示身份、角色和授权：

```powershell
& '.\.venv\Scripts\python.exe' -m alembic upgrade head
& '.\.venv\Scripts\python.exe' scripts\bootstrap_u0.py
```

应用启动时只校验数据库迁移版本，不会自动建表或写入演示数据。

## 启动 U0 API

```powershell
$env:PYTHONPATH = "$PWD\apps\api;$PWD\src"
& '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

OpenAPI 地址：`http://127.0.0.1:8000/docs`。

## 自动化测试

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

安装并启动 Docker Desktop 后，可验证 PostgreSQL 16 上的 Alembic 升级、降级和再次升级：

```powershell
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\scripts\test_postgres_migrations.ps1'
```

该脚本只管理 Compose 项目 `drone-u0-persistence-test`，结束时自动移除测试容器。通过此冒烟测试不代表政务云生产数据库验收通过。

## 本地 Web Demo

```powershell
& '.\.venv\Scripts\python.exe' scripts\serve_web_demo.py
```

访问 `http://127.0.0.1:8765`。演示环境和账号说明见 `docs/50-demo/演示环境与账号说明.md`。
