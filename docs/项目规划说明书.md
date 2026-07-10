# TandOrbit 项目规划说明书（V1.0）

---

# TandOrbit —— 双机双屏智能协同管理平台

**Version：1.0（规划版）**

**作者：Shuheng Cao**

**定位：Mac + Windows 双机双屏一体化协同解决方案**

---

# 一、项目背景

随着越来越多的开发者、设计师、办公人员采用 **Mac + Windows 双机办公** 模式，传统 KVM 切换器逐渐暴露出诸多不足：

* 切换速度慢
* 高刷新率支持有限
* Type-C 一线通支持不完善
* 显示器自动识别无法充分利用
* 多显示器配置复杂
* 无法满足"一机双屏 + 双机共享"等特殊办公场景

与此同时，大量国产显示器已经具备：

* 自动输入源切换（Auto Input）
* Type-C 视频输入
* USB Hub/KVM
* DDC/CI 控制能力

这些能力如果能够结合软件进行统一管理，将能够完全摆脱传统 KVM 的限制，实现更加智能、更加自然的双机协同体验。

因此，本项目提出 **TandOrbit**，通过软件统一管理两台计算机、两台显示器及外设，实现真正意义上的"无感切换"。

---

# 二、项目目标

TandOrbit 的核心目标只有一句话：

> **让两台电脑像一台电脑一样自然工作。**

用户无需：

* 手动切换输入源
* 调整显示模式
* 拔插 USB
* 修改 Deskflow 设置
* 更改音频输出
* 唤醒另一台电脑

所有操作均由软件自动完成。

---

# 三、设计理念

TandOrbit 遵循四个设计原则：

### 1. 无感切换（Seamless）

切换过程中无需用户进行任何额外操作。

例如：

```
按下快捷键

↓

Mac 自动关闭副屏

↓

Windows 自动恢复显示

↓

Deskflow 自动同步

↓

KVM 自动切换

↓

全部完成
```

整个过程控制在 2 秒以内。

---

### 2. 软件优先（Software First）

充分利用已有硬件能力，而非增加新的硬件。

例如：

* BetterDisplay
* MultiMonitorTool
* Deskflow
* Wake on LAN
* AppleScript
* PowerShell
* DDC/CI

通过软件组合实现完整体验。

---

### 3. 状态驱动（State Driven）

TandOrbit 不再执行"一堆脚本"，而是维护一套统一状态机。

例如：

```
当前状态

MAC_MODE

↓

目标状态

SHARE_MODE

↓

自动计算需要执行哪些动作
```

而不是：

```
执行脚本A

执行脚本B

执行脚本C
```

状态机能够保证每一次切换都具备一致性和可恢复性。

---

### 4. 可扩展（Extensible）

所有设备均采用插件化设计。

例如：

```
Display Controller

├── BetterDisplay
├── DDC/CI
├── MonitorControl
└── Lunar
```

未来可支持更多软件。

---

# 四、系统架构

```
                           TandOrbit

                 Python + PySide6 GUI

                          │
          ┌───────────────┴───────────────┐
          │                               │
      macOS Client                  Windows Agent
          │                               │
 BetterDisplay CLI               MultiMonitorTool
 AppleScript                     PowerShell
 pmset                           WinAPI
 MonitorControl                  Wake on LAN
          │                               │
          └────────────SSH/API────────────┘
```

Mac 作为主控制端。

Windows 作为 Agent。

所有操作由 TandOrbit 统一调度。

---

# 五、核心功能

## 1、显示器管理

支持：

* 启用显示器
* 禁用显示器
* 恢复布局
* 双屏扩展
* 双屏复制
* 单屏模式
* 主显示器切换

支持保存多个显示配置。

例如：

```
Mac 双屏

Windows 双屏

双机共享

会议模式

演示模式
```

---

## 2、设备切换

自动管理：

* KVM
* USB Hub
* 显示器输入源
* 自动输入检测

无需人工干预。

---

## 3、Deskflow 管理

自动：

* 启动
* 停止
* 重连
* 检测连接状态

保证鼠标键盘始终处于正确状态。

---

## 4、电源管理

自动控制：

Mac：

* Sleep
* Wake
* Display Sleep

Windows：

* Wake on LAN
* Sleep
* Hibernate

保证另一台电脑始终可以快速恢复。

---

## 5、音频管理

自动切换：

```
Mac

↓

AirPods

Windows

↓

USB DAC
```

无需重新选择输出设备。

---

## 6、剪贴板同步

提供双向同步：

```
Mac Copy

↓

Windows Paste

Windows Copy

↓

Mac Paste
```

支持：

* 文本
* 图片（规划）
* 文件（规划）

---

# 六、工作模式

## 模式一：Mac 工作模式

```
Display1 → Mac

Display2 → Mac
```

Windows 后台待机。

---

## 模式二：Windows 工作模式

```
Display1 → Windows

Display2 → Windows
```

Mac 自动休眠。

---

## 模式三：Share 模式

```
Display1 → Mac

Display2 → Windows
```

鼠标可自由跨平台移动。

两个系统同时工作。

这是 TandOrbit 最具特色的模式。

---

## 模式四：Presentation（规划）

```
Mac

↓

Windows

同时镜像到会议屏
```

适用于会议演示。

---

# 七、状态机设计

系统维护统一状态。

```
UNKNOWN

↓

MAC_MODE

↓

WINDOWS_MODE

↓

SHARE_MODE

↓

PRESENTATION_MODE
```

任何切换均按照：

```
当前状态

↓

目标状态

↓

计算差异

↓

执行动作

↓

验证状态

↓

完成
```

保证系统稳定。

---

# 八、软件界面

整体采用极简设计。

```
────────────────────────

        TandOrbit

Mac

● Online

Windows

● Online

Deskflow

● Connected

────────────────────────

● Mac

○ Windows

○ Share

────────────────────────

Ctrl+Alt+1

Ctrl+Alt+2

Ctrl+Alt+3

────────────────────────
```

用户无需理解复杂配置。

---

# 九、技术架构

| 模块         | 技术方案                                |
| ---------- | ----------------------------------- |
| GUI        | PySide6                             |
| 后端         | Python 3.13                         |
| 通信         | SSH + HTTP API（后续可支持 WebSocket）     |
| Windows 控制 | MultiMonitorTool、PowerShell、WinAPI  |
| macOS 控制   | BetterDisplay CLI、AppleScript、pmset |
| 配置         | YAML                                |
| 日志         | Loguru                              |
| 数据模型       | Pydantic                            |
| 打包         | PyInstaller                         |

---

# 十、项目目录

```text
TandOrbit/
│
├── apps/
│   ├── mac_client/
│   └── windows_agent/
│
├── core/
│   ├── state_machine.py
│   ├── scheduler.py
│   ├── controller.py
│   └── events.py
│
├── plugins/
│   ├── betterdisplay/
│   ├── multimonitortool/
│   ├── deskflow/
│   ├── wol/
│   ├── audio/
│   └── ddc/
│
├── ui/
│
├── config/
│
├── resources/
│
└── docs/
```

---

# 十一、开发路线图

| 阶段          | 目标     | 预计成果                                    |
| ----------- | ------ | --------------------------------------- |
| Milestone 1 | 核心控制能力 | 完成双机切换、显示器管理、Deskflow 联动                |
| Milestone 2 | 图形界面   | 完成主界面、配置管理、日志查看                         |
| Milestone 3 | 自动化能力  | 支持自动检测、状态同步、异常恢复                        |
| Milestone 4 | 高级功能   | 支持 DDC/CI、音频切换、剪贴板同步、全局快捷键              |
| Milestone 5 | 发布版    | 提供 macOS `.app`、Windows `.exe` 安装包及完整文档 |

---

# 十二、未来规划

TandOrbit 不仅是一个双机切换工具，更希望成为一个**跨平台桌面协同中枢**。未来可继续扩展：

* **多设备支持**：支持 3～4 台电脑（如 Mac mini、MacBook、Windows 主机、Linux 服务器）统一管理。
* **远程控制**：通过 Web 界面或移动端远程切换工作模式。
* **智能场景**：根据时间、网络、连接状态自动切换（例如连接 MacBook 即自动进入移动办公模式）。
* **插件生态**：开放插件接口，支持第三方开发音频、灯光、智能家居、会议设备等联动。
* **设备发现**：自动识别局域网中的 Agent，无需手动配置。
* **云同步**：同步配置、快捷键和场景，实现多套办公环境快速迁移。

---

# 十三、项目愿景

> **TandOrbit 希望重新定义双机办公体验。**

它不是传统意义上的 KVM 软件，也不是显示器控制工具，而是一个围绕**状态管理、自动协同、智能调度**构建的桌面协同平台。

通过统一管理显示器、键鼠、音频、电源、网络和系统状态，TandOrbit 将复杂的双机操作抽象为简单的工作模式切换，让用户只需关注工作本身，而无需关注设备之间的边界。未来，它将逐步发展为一个开放、可扩展的跨平台桌面协同生态，为多设备办公提供一致、高效、无感的使用体验。
