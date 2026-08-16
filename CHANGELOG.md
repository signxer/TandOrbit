# Changelog

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
