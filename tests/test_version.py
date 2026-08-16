"""版本号一致性测试：运行时版本 == pyproject.toml 版本 == release tag 前缀"""

import re
from pathlib import Path

from app.updater import __version__

_ROOT = Path(__file__).resolve().parent.parent


def test_runtime_version_matches_pyproject() -> None:
    """app/updater.__version__ 必须与 pyproject.toml 的 version 一致"""
    pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version = "([^"]+)"', pyproject, re.M)
    assert m, "pyproject.toml 缺少 version 字段"
    assert m.group(1) == __version__, (
        f"版本不一致: updater={__version__} pyproject={m.group(1)}"
    )


def test_version_format() -> None:
    """版本号必须形如 X.Y.Z（可带 v 前缀，供 release tag 使用）"""
    import re

    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), f"非法版本号: {__version__}"
