"""TandOrbit 数据模型"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.enums import DeviceStatus, DisplayMode, InputSource, Mode


class DisplayInfo(BaseModel):
    """显示器信息"""

    id: int
    name: str
    width: int = 0
    height: int = 0
    refresh_rate: float = 60.0
    is_primary: bool = False
    is_enabled: bool = True
    input_source: InputSource = InputSource.UNKNOWN


class DisplayProfile(BaseModel):
    """显示配置方案"""

    name: str
    description: str = ""
    displays: list[DisplayInfo] = Field(default_factory=list)
    display_mode: DisplayMode = DisplayMode.EXTEND
    primary_display_id: int = 1


class DeviceInfo(BaseModel):
    """设备信息"""

    name: str
    hostname: str
    ip_address: str = ""
    mac_address: str = ""
    status: DeviceStatus = DeviceStatus.UNKNOWN
    os_type: str = ""  # "macos" or "windows"
    deskflow_running: bool = False


class SystemState(BaseModel):
    """系统全局状态"""

    current_mode: Mode = Mode.UNKNOWN
    target_mode: Optional[Mode] = None
    mac_device: DeviceInfo = Field(
        default_factory=lambda: DeviceInfo(name="Mac", hostname="mac", os_type="macos")
    )
    windows_device: DeviceInfo = Field(
        default_factory=lambda: DeviceInfo(
            name="Windows", hostname="windows", os_type="windows"
        )
    )
    active_profile: str = ""
    deskflow_connected: bool = False
    transitioning: bool = False


class ActionRecord(BaseModel):
    """动作执行记录"""

    name: str
    status: str = "pending"
    error: str = ""
    duration_ms: float = 0.0
    details: dict[str, Any] = Field(default_factory=dict)


class ModeTransition(BaseModel):
    """模式切换记录"""

    from_mode: Mode
    to_mode: Mode
    actions: list[ActionRecord] = Field(default_factory=list)
    success: bool = False
    error: str = ""
    total_duration_ms: float = 0.0


class AgentResponse(BaseModel):
    """Windows Agent 响应"""

    success: bool
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class AgentHealthStatus(BaseModel):
    """Windows Agent 健康状态"""

    status: str = "ok"
    uptime_seconds: float = 0.0
    displays: list[DisplayInfo] = Field(default_factory=list)
    deskflow_running: bool = False
    deskflow_connected: bool = False
