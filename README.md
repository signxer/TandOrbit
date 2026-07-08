# TandOrbit

**双机双屏智能协同管理平台**

让两台电脑像一台电脑一样自然工作。

---

## 简介

TandOrbit 是一个针对 **macOS + Windows 双机双屏** 场景开发的桌面协同软件。通过统一管理两台计算机、两台显示器及外设，实现真正意义上的"无感切换"。

### 核心特性

- **无感切换** — 快捷键一键切换工作模式，全程自动
- **状态驱动** — 基于状态机的模式管理，保证一致性和可恢复性
- **插件架构** — 所有能力插件化，可扩展
- **双平台支持** — macOS 端控制 + Windows 端 Agent

### 工作模式

| 模式 | 说明 |
|------|------|
| Mac 模式 | 双屏均为 Mac，Windows 待机 |
| Windows 模式 | 双屏均为 Windows，Mac 休眠 |
| 共享模式 | 一屏 Mac，一屏 Windows，键鼠共享 |

---

## 架构

```
                     GUI (PySide6)
                           │
                    State Manager
                           │
                Scheduler / EventBus
                           │
           ┌───────────────┴───────────────┐
           │                               │
      Mac Client                     Windows Agent
           │                               │
    BetterDisplay                 MultiMonitorTool
    AppleScript                   PowerShell
    pmset                         WinAPI
           │                               │
           └──────── HTTP API ─────────────┘
```

---

## 安装

### 前置要求

- Python 3.11+
- macOS: [BetterDisplay](https://github.com/waydabber/BetterDisplay)
- Windows: [MultiMonitorTool](https://www.nirsoft.net/utils/multi_monitor_tool.html)
- 两台: [Deskflow](https://github.com/deskflow/deskflow)

### 安装依赖

```bash
pip install -r requirements.txt
```

或使用开发模式：

```bash
pip install -e ".[dev]"
```

---

## 使用

### Mac 端（主控端）

```bash
python -m app.main
```

### Windows 端（Agent）

```bash
python -m app.agent_main
```

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+Alt+1` | 切换到 Mac 模式 |
| `Ctrl+Alt+2` | 切换到 Windows 模式 |
| `Ctrl+Alt+3` | 切换到共享模式 |

---

## 配置

配置文件位于 `~/.tandorbit/config.yaml`：

```yaml
display:
  primary_id: 1
  secondary_id: 2

windows:
  host: "192.168.1.100"
  port: 5000

deskflow:
  auto_restart: true
  server_host: "192.168.1.100"
  server_port: 24800

audio:
  mac_output: "AirPods"
  windows_output: "USB DAC"
```

---

## 开发

### 运行测试

```bash
pytest
```

### 代码检查

```bash
ruff check .
mypy .
```

---

## 项目结构

```
TandOrbit/
├── app/
│   ├── gui/              # PySide6 界面
│   ├── controller/       # 控制器
│   ├── scheduler/        # 调度器和动作管道
│   ├── events/           # 事件总线
│   ├── state/            # 状态机
│   ├── communication/    # 双机通信
│   ├── main.py           # Mac 端入口
│   └── agent_main.py     # Windows 端入口
├── plugins/
│   ├── betterdisplay/    # macOS 显示器控制
│   ├── multimonitortool/ # Windows 显示器控制
│   ├── deskflow/         # 键鼠共享
│   ├── wol/              # Wake on LAN
│   ├── audio/            # 音频管理
│   ├── clipboard/        # 剪贴板同步
│   └── ddc/              # DDC/CI 控制
├── config/               # 默认配置
├── tests/                # 单元测试
└── docs/                 # 文档
```

---

## 开发里程碑

| 阶段 | 目标 |
|------|------|
| M1 | 基础框架（GUI、配置、日志、插件系统、状态机） |
| M2 | macOS 控制（BetterDisplay CLI 封装） |
| M3 | Windows Agent（HTTP API、显示模式切换） |
| M4 | 模式切换（Mac/Windows/Share 三种模式一键切换） |
| M5 | 稳定性（自动检测、异常恢复、打包发布） |

---

## 下载

### 预编译安装包

前往 [Releases](https://github.com/signxer/TandOrbit/releases) 页面下载：

- **macOS**: `TandOrbit-macOS.dmg`
- **Windows**: `TandOrbit-Windows.zip`

### 从源码构建

```bash
# macOS
pyinstaller tandorbit.spec --noconfirm

# Windows
pyinstaller tandorbit_agent.spec --noconfirm
```

### GitHub Actions 自动构建

项目配置了 GitHub Actions，推送 `v*` 标签时自动构建：

```bash
# 创建标签并推送
git tag v1.0.0
git push origin v1.0.0
```

Actions 会自动：
1. 运行测试
2. 构建 macOS `.app` 和 `.dmg`
3. 构建 Windows `.exe`
4. 创建 GitHub Release 并上传安装包

---

## 文档

- [使用说明](docs/使用说明.md) — 详细的安装和使用指南
- [项目规划说明书](TandOrbit%20项目规划说明书.md) — 项目背景和目标
- [软件设计说明书](软件设计说明书.md) — 技术架构设计

---

## 许可证

MIT License
