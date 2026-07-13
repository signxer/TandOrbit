"""TandOrbit 更新检查

通过 GitHub Releases API 检查是否有新版本。
"""

from __future__ import annotations

import platform

import httpx
from loguru import logger

# 当前版本 — 与 pyproject.toml / GitHub Release tag 保持一致
__version__ = "1.6.3"

GITHUB_REPO = "signxer/TandOrbit"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"


def _parse_version(v: str) -> tuple[int, ...]:
    """将版本号字符串解析为可比较的元组"""
    v = v.lstrip("v")
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0,)


async def check_update() -> dict | None:
    """检查是否有新版本

    Returns:
        dict with keys: tag_name, html_url, body, published_at
        None if no update or check failed
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                RELEASES_API,
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code != 200:
                logger.warning(f"Update check failed: HTTP {resp.status_code}")
                return None

            data = resp.json()
            remote_tag = data.get("tag_name", "")
            remote_ver = _parse_version(remote_tag)
            local_ver = _parse_version(__version__)

            if remote_ver > local_ver:
                logger.info(f"New version available: {remote_tag} (current: {__version__})")
                return {
                    "tag_name": remote_tag,
                    "html_url": data.get("html_url", RELEASES_URL),
                    "body": data.get("body", ""),
                    "published_at": data.get("published_at", ""),
                }

            logger.info(f"Already up to date: {__version__}")
            return None

    except Exception as e:
        logger.warning(f"Update check error: {e}")
        return None


def get_download_assets(release: dict) -> list[dict]:
    """从 release 数据中提取下载链接"""
    assets = release.get("assets", [])
    system = platform.system()
    result = []
    for asset in assets:
        name = asset.get("name", "")
        url = asset.get("browser_download_url", "")
        if system == "Darwin" and name.endswith(".dmg"):
            result.append({"name": name, "url": url, "platform": "macOS"})
        elif system == "Windows" and name.endswith(".zip"):
            result.append({"name": name, "url": url, "platform": "Windows"})
    # 如果没有匹配的平台，返回所有
    if not result:
        for asset in assets:
            result.append({
                "name": asset.get("name", ""),
                "url": asset.get("browser_download_url", ""),
                "platform": "Other",
            })
    return result
