"""TandOrbit 核心枚举定义"""

from enum import Enum, auto


class Mode(Enum):
    """工作模式枚举"""

    MAC = auto()
    WINDOWS = auto()
    SHARE = auto()
    PRESENTATION = auto()
    UNKNOWN = auto()


class DisplayMode(Enum):
    """显示模式枚举"""

    EXTEND = auto()
    DUPLICATE = auto()
    SINGLE = auto()


class DeviceStatus(Enum):
    """设备状态枚举"""

    ONLINE = auto()
    OFFLINE = auto()
    UNKNOWN = auto()
    SLEEPING = auto()


class ActionStatus(Enum):
    """动作执行状态"""

    PENDING = auto()
    RUNNING = auto()
    SUCCESS = auto()
    FAILED = auto()
    ROLLED_BACK = auto()


class PluginStatus(Enum):
    """插件状态"""

    REGISTERED = auto()
    INITIALIZED = auto()
    ENABLED = auto()
    DISABLED = auto()
    ERROR = auto()


class InputSource(Enum):
    """显示器输入源"""

    HDMI1 = "hdmi1"
    HDMI2 = "hdmi2"
    DISPLAYPORT1 = "dp1"
    DISPLAYPORT2 = "dp2"
    TYPE_C = "usbc"
    VGA = "vga"
    UNKNOWN = "unknown"
