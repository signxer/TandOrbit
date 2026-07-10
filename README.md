<p align="center">
  <img src="resources/icon.png" width="120" alt="TandOrbit Logo">
</p>

<h1 align="center">TandOrbit</h1>

<p align="center">
  <strong>双机双屏智能协同管理平台</strong>
</p>

<p align="center">
  让两台电脑像一台电脑一样自然工作
</p>

<p align="center">
  <a href="https://github.com/signxer/TandOrbit/releases"><img src="https://img.shields.io/github/v/release/signxer/TandOrbit?style=flat-square&color=blue" alt="Release"></a>
  <a href="https://github.com/signxer/TandOrbit/actions"><img src="https://img.shields.io/github/actions/workflow/status/signxer/TandOrbit/build.yml?style=flat-square&label=build" alt="Build"></a>
  <a href="https://github.com/signxer/TandOrbit/blob/main/LICENSE"><img src="https://img.shields.io/github/license/signxer/TandOrbit?style=flat-square&color=green" alt="License"></a>
  <a href="https://github.com/signxer/TandOrbit/stargazers"><img src="https://img.shields.io/github/stars/signxer/TandOrbit?style=flat-square" alt="Stars"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/PySide6-Qt_GUI-black?style=flat-square&logo=qt&logoColor=white" alt="PySide6">
  <img src="https://img.shields.io/badge/macOS-Sonoma+-black?style=flat-square&logo=apple&logoColor=white" alt="macOS">
  <img src="https://img.shields.io/badge/Windows-10%2F11-blue?style=flat-square&logo=windows&logoColor=white" alt="Windows">
  <img src="https://img.shields.io/badge/Deskflow-KVM_共享-green?style=flat-square" alt="Deskflow">
</p>

---

## ✨ 核心特性

- **🖥️ 无感切换** — 快捷键一键切换工作模式，显示器自动识别信号源
- **⌨️ 键鼠共享** — 通过 Deskflow 实现跨平台键鼠共享，鼠标自由穿越两屏
- **🔌 自动发现** — UDP 广播自动发现对端，无需手动配置 IP 和端口
- **🧩 插件架构** — 所有能力插件化，按平台加载，可扩展
- **🔋 电源管理** — WoL 远程唤醒 + 自动休眠，省电省心

## 🎯 工作模式

| 模式 | Mac | Windows | 键鼠 | 场景 |
|:----:|:---:|:-------:|:----:|------|
| **Mac** | 双屏 ✅ | 休眠 💤 | — | 纯 Mac 工作 |
| **Windows** | 休眠 💤 | 双屏 ✅ | — | 纯 Windows 工作 |
| **共享** | 主屏 ✅ | 副屏 ✅ | 共享 ⌨️ | 同时使用两台机器 |

---

## 📦 安装

### 下载预编译包（推荐）

前往 **[Releases](https://github.com/signxer/TandOrbit/releases)** 下载：

| 平台 | 文件 |
|------|------|
| macOS | `TandOrbit-macOS.dmg` |
| Windows | `TandOrbit-Windows.zip` |

**macOS 首次安装**需要授权：

```bash
sudo xattr -rd com.apple.quarantine /Applications/TandOrbit.app
```

### 从源码运行

```bash
git clone https://github.com/signxer/TandOrbit.git
cd TandOrbit
pip install -r requirements.txt
python -m app.main
```

### 前置工具

| 工具 | 平台 | 用途 | 下载 |
|------|:----:|------|------|
| [BetterDisplay](https://github.com/waydabber/BetterDisplay) | macOS | 显示器控制 | ↗ |
| [MultiMonitorTool](https://www.nirsoft.net/utils/multi_monitor_tool.html) | Windows | 显示器管理 | ↗ |
| [Deskflow](https://github.com/deskflow/deskflow) | 双端 | 键鼠共享 | ↗ |

> 启动时会自动检查依赖，缺失的工具会提供下载链接。

---

## ⌨️ 快捷键

| macOS | Windows | 功能 |
|:-----:|:-------:|------|
| `⌃⌥1` | `Ctrl+Alt+1` | 切换到 Mac 模式 |
| `⌃⌥2` | `Ctrl+Alt+2` | 切换到 Windows 模式 |
| `⌃⌥3` | `Ctrl+Alt+3` | 切换到共享模式 |

---

## 🏗️ 架构

```
        ┌──────────── Mac (主控) ────────────┐
        │                                     │
        │  GUI (PySide6)                      │
        │    ↕                                │
        │  Controller → ActionPipeline        │
        │    ↕           ↕                    │
        │  StateManager  EventBus             │
        │    ↕           ↕                    │
        │  AgentServer    MacClient ──HTTP──► Windows AgentServer
        │  (port 5001)              ◄──HTTP──  (port 5000)
        │                                     │
        │  Plugins:                           │
        │  · BetterDisplay    · Deskflow      │
        │  · WoL              · DDC/CI        │
        └─────────────────────────────────────┘
```

---

## 📁 项目结构

```
TandOrbit/
├── app/                    # 应用代码
│   ├── gui/                # PySide6 界面
│   ├── controller/         # 控制器（唯一入口）
│   ├── scheduler/          # 动作管道（Pipeline + Action）
│   ├── state/              # 状态机
│   ├── communication/      # 双机通信（HTTP + UDP 发现）
│   ├── config.py           # 配置管理
│   └── main.py             # 入口（Mac + Windows 共用）
├── plugins/                # 插件
│   ├── betterdisplay/      # macOS 显示器控制
│   ├── multimonitortool/   # Windows 显示器管理
│   ├── deskflow/           # 键鼠共享
│   ├── wol/                # Wake on LAN
│   ├── audio/              # 音频设备切换
│   ├── clipboard/          # 剪贴板同步
│   └── ddc/                # DDC/CI 显示器控制
├── packaging/              # PyInstaller 打包配置
├── config/                 # 默认配置
├── scripts/                # 工具脚本
├── tests/                  # 单元测试
└── docs/                   # 文档
```

---

## 📖 文档

- [使用说明](docs/使用说明.md) — 安装、配置和使用指南
- [项目规划说明书](docs/项目规划说明书.md) — 项目背景和目标
- [软件设计说明书](docs/软件设计说明书.md) — 技术架构设计

---

## 🛠️ 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 代码检查
ruff check .
mypy .

# 从源码构建
pyinstaller packaging/tandorbit.spec --noconfirm
```

---

## 📄 许可证

[MIT License](LICENSE) · © [signxer](https://github.com/signxer)
