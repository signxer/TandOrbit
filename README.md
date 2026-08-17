<p align="center">
  <img src="resources/icon.png" width="120" alt="TandOrbit Logo">
</p>

<h1 align="center">TandOrbit</h1>

<p align="center">
  <strong>双机双屏智能协同管理平台</strong> · 让两台电脑像一台电脑一样自然工作
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

## 📖 简介

TandOrbit 是一款 **Mac + Windows 双机双屏协同工具**：两台电脑各接两台显示器，通过一个托盘应用 + 全局快捷键，在「纯 Mac 工作」「纯 Windows 工作」「两台同时使用」三种模式间一键切换，并配合 Deskflow 实现跨平台键鼠共享。

它解决的问题：

- 桌面上两台电脑、两台显示器，每次切换都要手动按显示器按钮、换键鼠 —— 太繁琐；
- 双机协同场景（Mac 写代码 + Windows 跑测试）希望键鼠、屏幕无缝流转；
- 切换失败时无从排查（不知道哪一步失败了）。

TandOrbit 的做法：**全局快捷键一键切换**、**每台机器自动控制自己的显示器**、**切换过程可观测**（历史记录 + 成功率看板 + 日志）。

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🖥️ **一键无感切换** | 全局快捷键（系统级，任意前台应用可用）在 Mac / Windows / 共享模式间切换，显示器自动切换信号源 |
| 📊 **切换记录与成功率** | 最近切换历史（SQLite 持久化，重启不丢）与成功率看板，托盘一键打开，切换问题不再靠猜 |
| ⚔️ **切换冲突仲裁** | 两端同时发起切换时自动排队，避免动作并发互相干扰 |
| ⌨️ **键鼠共享** | 基于 Deskflow，鼠标键盘在两台电脑间无缝穿越（共享模式） |
| 🔌 **自动发现** | UDP 广播自动发现对端，无需手动配置 IP 和端口；对端地址变化自动更新 |
| 🔋 **电源管理** | WoL 远程唤醒（多网卡定向广播）+ 一键关闭显示器，省电省心 |
| 🛡️ **自动输入识别保护** | 不主动改写显示器输入源，只控制两台电脑的显示输出，保持显示器自动识别始终可用 |
| 🔐 **Agent 鉴权**（可选） | 配置访问令牌后，未授权设备无法控制本机 |
| 🧩 **插件架构** | 所有能力插件化、按平台加载，易扩展 |
| 🛠️ **可观测性** | 应用内日志查看器、配置导入/导出、启动自检与可选自愈 |

---

## 🎯 工作模式

| 模式 | Mac 显示器 | Windows 显示器 | 键鼠 | 适用场景 |
|:----:|:---------:|:-------------:|:----:|---------|
| **Mac** | 双屏 ✅ | 关闭 | — | 纯 Mac 工作 |
| **Windows** | 休眠 | 双屏 ✅ | — | 纯 Windows 工作 |
| **共享** | 主屏 ✅ | 副屏 ✅ | 共享 ⌨️ | 同时使用两台机器 |

> 原理：每台机器只控制**自己**的显示器（Mac 用 BetterDisplay、Windows 用 MultiMonitorTool / Windows API）。
> 切换时一台机器的信号消失、另一台点亮，显示器自动跟随活跃信号源。
> TandOrbit **不会主动修改显示器输入源**，避免关闭显示器自身的自动输入识别。

---

## 🚀 快速开始

### 1. 安装

前往 **[Releases](https://github.com/signxer/TandOrbit/releases)** 下载对应平台的安装包：

| 平台 | 文件 |
|------|------|
| macOS | `TandOrbit-macOS.dmg` |
| Windows | `TandOrbit-Windows.zip`（解压后运行 `TandOrbit.exe`） |

**macOS 首次打开**需解除隔离（未签名应用）：

```bash
sudo xattr -rd com.apple.quarantine /Applications/TandOrbit.app
```

**Windows 可选**：把 TandOrbit 注册为开机自启（计划任务），登录后自动就绪、随时响应 Mac 端的 WoL 唤醒与切换指令：

```bat
scripts\install_agent.bat      # 以管理员身份运行
```

### 2. 前置依赖

启动时会自动检查依赖，缺失的工具会弹出下载链接：

| 工具 | 平台 | 用途 | 必需性 |
|------|:----:|------|:------:|
| [BetterDisplay](https://github.com/waydabber/BetterDisplay) | macOS | 显示器启用/禁用控制（断连副屏需要 Pro 授权） | 必需 |
| [MultiMonitorTool](https://www.nirsoft.net/utils/multi_monitor_tool.html) | Windows | 显示器启用/禁用管理 | 必需 |
| [Deskflow](https://github.com/deskflow/deskflow) | 双端 | 键鼠共享（共享模式） | 必需 |
| [ControlMyMonitor](https://www.nirsoft.net/utils/control_my_monitor.html) | Windows | DDC/CI 亮度/电源等辅助控制（不用于自动输入切换） | 可选 |

> 两台机器都需要安装 Deskflow 并保持同一局域网；Deskflow 服务端默认运行在 Windows（可在配置中调整）。

### 3. 首次配置

1. 两台机器各启动 TandOrbit，确认托盘图标出现、状态栏绿灯（自动发现对端）；
2. 打开 **设置 → 显示器**，确认主/副显示器编号正确（可点「刷新」从本机枚举）；
3. 在 **设置 → 快捷键** 录制（或确认默认）三组切换快捷键；
4. TandOrbit **不会主动修改显示器输入源**，以保持显示器自己的自动识别功能；如需手动诊断，可单独使用显示器厂商工具。

### 4. macOS 权限

全局快捷键需要**辅助功能**权限：

> 系统设置 → 隐私与安全性 → 辅助功能 → 勾选 TandOrbit

未授权时应用正常运行，但全局快捷键不可用（日志会提示）。

---

## ⌨️ 使用指南

### 模式切换

| 方式 | 操作 |
|------|------|
| **全局快捷键** | macOS `Ctrl+Option+1/2/3` · Windows `Ctrl+Alt+1/2/3`（可在设置中自定义） |
| **主窗口** | 点击 Mac / Windows / 共享 按钮 |
| **托盘菜单** | 右键托盘图标 → 模式菜单 |

切换期间模式按钮会显示加载动画并暂时禁用，完成后自动恢复。

### 切换记录与成功率

托盘 → **切换记录…**：查看最近 20 次切换的成功率、每次切换的耗时与失败原因，定位问题（如「某一步动作失败」）非常直接。

### 键鼠共享（Deskflow）

进入**共享模式**后 TandOrbit 自动启动 Deskflow：Mac 主屏 + Windows 副屏，鼠标键盘在两屏间无缝穿越；离开共享模式自动停止。

### 唤醒与休眠

- **唤醒**：切换到 Windows / 共享模式时若对端离线，会询问是否发送 WoL 唤醒包（自动向所有网卡广播）；
- **休眠显示器**：主窗口或托盘可一键关闭显示器（不休眠电脑）。

### 日志与排障

托盘 → **查看日志**：应用内实时查看日志（亦可打开日志文件）。日志目录：`~/.tandorbit/logs/`。

---

## 🏗️ 架构

```
        ┌──────────────── Mac（主控）────────────────┐
        │                                             │
        │  GUI（PySide6）                             │
        │    ↕                                        │
        │  Controller → ActionPipeline                │
        │    ↕            ↕                           │
        │  StateManager   EventBus                    │
        │    ↕            ↕                           │
        │  AgentServer    MacClient ──HTTP──► Windows AgentServer
        │  (port 5001)               ◄──HTTP──  (port 5000)
        │                                             │
        │  Plugins:                                   │
        │  · BetterDisplay  · Deskflow  · WoL        │
        │  · DDC/CI（可选）  · Audio                  │
        └─────────────────────────────────────────────┘
```

| 端口 | 用途 |
|:----:|------|
| `5000` | Windows Agent HTTP 服务（接收 Mac 控制指令） |
| `5001` | Mac Agent HTTP 服务（接收 Windows 控制指令） |
| `5002` | UDP 广播自动发现 |
| `24800` | Deskflow 键鼠共享 |

模式切换 = **双端对称执行**：本机运行动作管线（显示器、Deskflow、音频等），并把目标模式同步给对端，对端执行自己的显示器配置；切换完成后进行端到端验证（轮询对端真实显示器状态），失败自动重试。

---

## ⚙️ 配置

配置文件：`~/.tandorbit/config.yaml`（首次启动自动生成；设置对话框会维护大部分字段）。

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `display.primary_id` / `secondary_id` | `1` / `2` | 主/副显示器编号（Windows DISPLAY 编号） |
| `display.share_display_id` | `2` | 共享模式留给 Windows 的显示器 |
| `display.auto_repair` | `false` | 启动时按上次模式自愈显示器状态 |
| `display.auto_repair` | `false` | 启动时按上次模式自愈显示器状态；不会修改显示器输入源 |
| `display.windows_primary_monitor_id` | `""` | Windows 主显示器 Monitor ID（可选，避免 DISPLAY 编号漂移，设置页可复制） |
| `display.windows_secondary_monitor_id` | `""` | Windows 副显示器 Monitor ID（可选） |
| `windows.host` / `port` | `192.168.1.100` / `5000` | Windows 端地址（自动发现可覆盖） |
| `windows.mac_address` | `""` | Windows 网卡 MAC（WoL 唤醒用） |
| `agent_token` | `""` | Agent 访问令牌（两端需一致；空 = 不鉴权）。设置后未授权设备无法控制本机 |
| `deskflow.server_host` / `server_port` | Windows IP / `24800` | Deskflow 服务端地址 |
| `deskflow.is_server` | 自动 | Windows 端默认为服务端，Mac 端为客户端 |
| `audio.mac_output` / `windows_output` | `"AirPods"` / `"USB DAC"` | 切换模式时自动切换的音频输出设备 |
| `hotkeys.switch_*` | `Ctrl+Alt+1/2/3` | 全局快捷键（macOS 默认 `Ctrl+Option`） |
| `last_mode` | `null` | 上次成功切换的模式（启动恢复） |

---

## 🩺 排障指南

| 症状 | 排查 |
|------|------|
| 切换后屏幕没反应 | 打开「切换记录…」看失败动作；看「查看日志」；确认对端 Agent 在线（状态栏绿灯） |
| 全局快捷键无效 | macOS：检查「辅助功能」授权；Windows：检查快捷键是否被其他软件占用（设置里会提示注册失败） |
| 对端一直显示离线 | 确认同一局域网；检查防火墙是否放行 `5000/5001/5002` 端口（Windows 首次运行需允许） |
| 打开后提示隔离/无法运行（macOS） | 执行 `sudo xattr -rd com.apple.quarantine /Applications/TandOrbit.app` |
| 显示器没有自动切换 | 保持显示器的自动输入检测开启；TandOrbit 不会主动写入 DDC 输入源。确认两台电脑的显示输出按模式正确启用/关闭 |
| 共享模式副屏不亮 | 确认 BetterDisplay 已授权「断连显示器」能力（Pro）；确认 Windows 端主屏被正确禁用（切换记录里看验证结果） |

---

## 🛠️ 开发

### 环境

- Python 3.11+

```bash
git clone https://github.com/signxer/TandOrbit.git
cd TandOrbit
pip install -e ".[dev]"
python -m app.main          # 运行（Mac / Windows 共用入口）
```

### 测试与检查

```bash
pytest                      # 单元测试
ruff check .                # 代码规范
mypy .                      # 类型检查
```

### 构建与发布

```bash
pyinstaller packaging/tandorbit.spec --noconfirm
```

CI（GitHub Actions）在打 `v*` tag 时自动构建 macOS dmg + Windows zip 并发布到 Releases。

### 项目结构

```
TandOrbit/
├── app/                    # 应用代码
│   ├── gui/                # PySide6 界面（主窗口/托盘/设置/日志/切换看板）
│   ├── controller/         # 控制器（唯一入口，切换编排）
│   ├── scheduler/          # 动作管道（Pipeline + Action）
│   ├── state/              # 状态机
│   ├── communication/      # 双机通信（HTTP Agent + UDP 发现）
│   ├── hotkeys.py          # 双平台全局快捷键
│   ├── config.py           # 配置管理
│   └── main.py             # 入口（Mac + Windows 共用）
├── plugins/                # 插件（按平台加载）
│   ├── betterdisplay/      # macOS 显示器控制
│   ├── multimonitortool/   # Windows 显示器管理
│   ├── deskflow/           # 键鼠共享
│   ├── wol/                # Wake on LAN
│   ├── audio/              # 音频设备切换
│   └── ddc/                # DDC/CI 辅助控制（亮度/电源，不切输入源）
├── packaging/              # PyInstaller 打包配置
├── config/                 # 默认配置模板
├── scripts/                # 工具脚本（Agent 服务安装、打包辅助）
├── tests/                  # 单元测试
└── docs/                   # 使用说明与设计文档
```

---

## 📖 文档

- [使用说明](docs/使用说明.md) — 安装、配置与使用详解
- [更新日志](CHANGELOG.md) — 版本变更记录
- [软件设计说明书](docs/软件设计说明书.md) — 技术架构设计
- [项目规划说明书](docs/项目规划说明书.md) — 项目背景与目标

---

## 📄 许可证

[MIT License](LICENSE) · © [signxer](https://github.com/signxer)

**TandOrbit 仅管理本机显示器与进程，不触碰用户数据；所有通信均在本机局域网内进行。**
