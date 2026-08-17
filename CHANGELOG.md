# Changelog

## [2.2.4] - 修复环境检查与枚举诊断

- 修复环境检查不读配置路径：`_check_multimonitortool` 改为同时检查配置路径，`RequirementsDialog` 接受 `config_manager` 参数。
- 修复枚举脚本中 `monitor_id`/`device_id` 为 null 时可能导致 `ConvertTo-Json` 失败的问题，加 `[string]` 强制转换。
- 增强 `list_displays` 诊断日志：空结果时输出脚本原始内容，便于定位枚举失败原因。
- 修复 MMT 初始化路径判断逻辑，消除对绝对路径的误警告。


## [2.2.3] - 修复版本号不同步

- 修复 `app/updater.py` 的 `__version__` 停留在 2.1.3，导致每次启动都提示有新版本。
- 版本号统一同步为 2.2.2；pyproject.toml 同步更新。
- CI 新增 `verify-version` 步骤：发布 tag 必须与代码版本一致，否则构建失败，防止再犯。

## [2.2.2] - 彻底修复 Windows 主窗口布局重叠

- 模式按钮高度改为自适应内容（不再固定 80px），任何字体/DPI 下图标与文字都不再被裁剪。
- 快捷键提示标签显式设置透明背景，避免与按钮视觉重合。
- Windows 端窗口高度 320→344，系统缩放时允许自动扩展。

## [2.2.1] - 修复 Windows 主窗口布局重叠

- 模式切换按钮上下 padding 12px→6px，释放内部空间，避免 Windows 大字体（Segoe UI）下按钮内容被下边缘裁剪并与快捷键提示重叠。
- 新增主窗口布局回归测试。


## [2.2.0] - 显示器身份绑定与拓扑恢复

- Windows 枚举增加 `monitor_id`/`device_id` 身份字段，支持按 Monitor ID 定位显示器，避免 DISPLAY 编号漂移。
- 新增配置 `windows_primary_monitor_id` / `windows_secondary_monitor_id`，验证与应用优先按身份解析，找不到才回退数字编号。
- 进入共享模式前保存 Windows 完整拓扑，退出时恢复（MultiMonitorTool /SaveConfig、/LoadConfig）。
- 新增 `/api/mode/current` 端点与周期状态对账，发现两端模式不一致时告警。
- 打包排除大量未使用的 Qt 模块，减小体积。


## [2.1.15] - 禁止自动 DDC 输入切换

- **移除所有自动 DDC 输入源控制**：不再调用 `set_input_source`/`get_input_source`，
  不再读取或保存 `input_map`，不再执行 DDC 输入源读回验证。
- 保持显示器自身的自动输入识别开启；TandOrbit 只控制两台电脑的显示输出拓扑。
- DDC 插件仅保留亮度、对比度、电源等辅助能力，不参与模式切换。

## [2.1.14] - 体检优化

- BetterDisplay 设置诊断现在显示最近一次 CLI 错误，便于区分路径、未运行和 Pro 能力问题。
- Agent 健康检查与 Mac 副屏解析失败改为记录明确 warning，不再静默吞掉异常。
- 清理 discovery 未使用导入。
- 远端模式持久化继续使用注入的 ConfigManager，避免重复加载配置。


## [2.1.13] - 整体体检修复

- 修复远端同步持久化 `last_mode` 时未先加载配置，可能把用户自定义配置覆盖为默认值的问题。
- AgentServer 注入共享 ConfigManager，减少重复读取配置文件。
- 配置导入提示需要重启的运行中组件。
- 补充远端配置保护回归测试。


## [2.1.5] - 修复 CI（根治）

- **asyncio_mode 改为 strict**：pytest-asyncio 1.4.0 在 Windows 上存在收尾 bug——
  最后一个测试为纯 sync 测试时，测试全过（91 passed, 12 skipped）但进程仍返回
  exit code 1，CI 误报失败。strict 模式下 sync 测试完全不经过 asyncio 插件，根除该问题。
- **锁定 pytest-asyncio<1.3**（使用验证过的 1.2.0），与 pytest<9 组合更稳定。

## [2.1.4] - 修复 CI

- **锁定 pytest<9**：pytest 9.1.1 + pytest-asyncio 1.4.0 在 Windows 上存在兼容问题
  （测试全过但进程仍以 exit code 1 结束，CI 误报失败）。pytest-asyncio 1.4.0 为
  最新版且只保证支持 pytest 8.x，故锁定 `pytest<9`、`pytest-asyncio<2`。

## [2.1.3] - 修复版本号

- **修复运行时版本号停留在 2.0.0**：`app/updater.py` 的 `__version__` 在 v2.1.x 发布时未同步
  更新，导致更新检查用旧版本号对比 GitHub tag，永远提示"发现新版本"。
- **版本号统一管理**：`packaging/tandorbit.spec` 与 CI 的 Info.plist 改为从
  `app/updater.py` 读取版本，打包版本与运行时版本不再可能不一致。
- 新增版本一致性测试（updater ↔ pyproject.toml）。

## [2.1.2] - 修复设置对话框崩溃

- **修复 `NameError: name 'threading' is not defined`**：`_refresh_displays`/`_refresh_audio`
  的 `import threading` 误写在内部 `_worker` 函数里，而 `threading.Thread(...)` 在函数外调用；
  已把 `threading`/`asyncio` 移到模块顶部。打开设置对话框即崩溃的问题修复。
- 新增设置对话框回归测试（offscreen Qt 真实实例化，覆盖异步刷新路径）。

## [2.1.1] - 打包修复

- **修复 Windows 打包报错 `No module named '_sqlite3'`**：PyInstaller 打包遗漏 sqlite3 的
  C 扩展。spec 与 macOS 命令行均显式加入 `sqlite3` / `_sqlite3`。
- **修复 Windows 打包无图标**：spec 的 `EXE` 补充 `icon=resources/icon.ico`。
- **切换历史存储优雅降级**：即使将来任一环境缺少 `_sqlite3`，应用也不再崩溃，
  自动退回内存模式（重启不保留，但功能可用）。
- 修复 `SwitchHistoryStore` 启动加载时的自锁死锁（非重入锁嵌套）。
- 修正打包版本号（`CFBundleShortVersionString` 1.1.1 → 2.1.1）。

## [2.1.0] - 安全与可靠性加固

### 🔐 安全

- **Agent 访问令牌鉴权**：可在设置中生成/配置 token（两端一致），未授权请求一律
  `401`（`/api/health` 放行供在线探测）；默认空 = 不鉴权，兼容旧配置。
  防止局域网内任意设备关闭显示器/关机。

### ⚡ 可靠性

- **DDC 输入源读回验证**：开启 DDC 输入切换后，切换完成会读回显示器真实输入源
  （VCP 0x60）做端到端校验，不匹配自动重切重试；不支持读回的显示器不误报。
- **切换冲突仲裁**：两端同时发起切换时，后发起方等待对端完成（`/api/mode/claim`
  声明 + 最长 30s 等待），避免双端动作并发执行互相干扰。

### 📊 可观测性

- **切换历史持久化**：切换记录落 SQLite（`~/.tandorbit/state.db`），重启不丢，
  成功率统计基于完整历史。

### 🧪 测试与 CI

- **Agent 冒烟测试**：双平台 CI 用 TestClient 实测 `/api/health`、无插件错误路径、
  token 鉴权、切换声明仲裁等端点。

## [2.0.0] - 大版本：补齐承诺 · 切换可靠 · 协同可用

### ✨ 新功能

- **全局快捷键（真实现）**：macOS 使用 Quartz CGEventTap、Windows 使用 RegisterHotKey，
  `Ctrl+Alt+1/2/3` 一键切换模式；支持设置中热更新、重复注册冲突提示。
  macOS 需在「系统设置 → 隐私与安全性 → 辅助功能」中授权。
- **切换记录看板**：托盘「切换记录…」查看最近 100 次切换的历史与成功率，
  定位「切换成功率不高」不再靠猜。
- **切换前预检**：切换前检查对端 Agent 与本机显示器插件可用性，提前中止并给出原因。
- **启动自检 + 模式持久化**：记住上次成功切换的模式，重启后恢复；
  `display.auto_repair`（默认关闭）可开启启动自愈。
- **DDC/CI 输入源切换**（配置驱动，默认关闭）：切换时主动把显示器输入源切到对应主机，
  替代依赖显示器「自动识别信号源」；需 m1ddc / ControlMyMonitor。
- **配置导入/导出**：设置对话框一键备份/迁移配置。
- **应用内日志查看器**：托盘「查看日志」实时查看应用日志（不再只是打开外部文件）。

### 🔧 修复与改进

- 修复点击当前模式按钮/托盘项误弹「切换失败」提示的回归；切换中禁用全部模式按钮。
- 在线探测改用 Agent HTTP（不再用可能被防火墙拦截的 ping），且不再阻塞 GUI 线程；
  修复 Windows 端探测对端时误用自身地址的问题。
- 自动发现更新对端地址后，客户端连接自动重建（不再连旧 IP）。
- 设置对话框显示器/音频列表改为后台加载，打开不再卡顿。
- `/api/health` 轻量化，降低频繁探测开销。
- WoL 自动向本机所有网卡的子网定向广播地址发送，提升唤醒成功率。
- 配置写入改为原子操作（临时文件 + rename），崩溃不损坏配置。
- 快捷键保存时校验非空且互不冲突。

### 🗑️ 移除

- 移除未实现的剪贴板同步空壳（`plugins/clipboard`）。
- 移除未实现的 PRESENTATION 演示模式（枚举/状态机/UI）。

### 📦 其他

- 版本号升级到 2.0.0。
