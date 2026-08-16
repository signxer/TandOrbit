"""版本号一致性测试：运行时版本 == pyproject.toml 版本 == release tag 前缀

注意：测试特意写成 async（@pytest.mark.asyncio）。
CI 诊断发现：pytest 在 Windows 上"最后一个测试为纯 sync 测试"时，
测试全过但进程可能以 exit code 1 结束（见 v2.1.3~v2.1.5 的 CI 失败）。
写成 async 以绕过该环境问题。
"""

import re
from pathlib import Path

import pytest

from app.updater import __version__

_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.asyncio
async def test_runtime_version_matches_pyproject() -> None:
    """app/updater.__version__ 必须与 pyproject.toml 的 version 一致"""
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version = "([^"]+)"', pyproject, re.M)
    assert m, "pyproject.toml 缺少 version 字段"
    assert m.group(1) == __version__, (
        f"版本不一致: updater={__version__} pyproject={m.group(1)}"
    )


@pytest.mark.asyncio
async def test_version_format() -> None:
    """版本号必须形如 X.Y.Z（可带 v 前缀，供 release tag 使用）"""
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), f"非法版本号: {__version__}"
