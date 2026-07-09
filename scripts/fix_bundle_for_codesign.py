"""修复 PyInstaller macOS bundle 结构。

PyInstaller 把所有文件（代码 + 数据）都放在 Contents/Frameworks/ 下，
但 macOS 代码签名要求 Frameworks/ 只包含可签名的代码文件。

此脚本将非代码文件从 Frameworks/ 移到 Resources/。
"""

import os
import shutil
import sys
from pathlib import Path

# 可签名的文件扩展名
SIGNABLE_EXTS = {'.dylib', '.so', '.pyd', ''}


def is_signable(path: Path) -> bool:
    """判断文件是否可签名（是代码文件）"""
    if path.is_dir():
        return True
    if path.suffix in SIGNABLE_EXTS:
        return True
    if not path.suffix and path.is_file():
        try:
            with open(path, 'rb') as f:
                magic = f.read(4)
            if magic in (b'\xfe\xed\xfa\xce', b'\xfe\xed\xfa\xcf',
                         b'\xce\xfa\xed\xfe', b'\xcf\xfa\xed\xfe',
                         b'\xca\xfe\xba\xbe'):
                return True
        except (OSError, IOError):
            pass
    return False


def fix_bundle(app_path: Path) -> None:
    """修复 app bundle 结构"""
    frameworks = app_path / 'Contents' / 'Frameworks'
    resources = app_path / 'Contents' / 'Resources'

    if not frameworks.exists():
        print(f"No Frameworks directory found at {frameworks}")
        return

    moved_count = 0

    # 遍历 Frameworks 下的所有文件（不跟随符号链接）
    for root, dirs, files in os.walk(frameworks, followlinks=False):
        root_path = Path(root)

        for fname in files:
            fpath = root_path / fname

            # 跳过符号链接
            if fpath.is_symlink():
                continue

            # 跳过可签名文件
            if is_signable(fpath):
                continue

            # 计算相对于 Frameworks 的路径
            rel = fpath.relative_to(frameworks)

            # 目标路径在 Resources 下
            dest = resources / rel
            dest.parent.mkdir(parents=True, exist_ok=True)

            try:
                # 如果目标已有同名文件或符号链接，先删除
                if dest.is_symlink() or dest.exists():
                    dest.unlink()
                shutil.move(str(fpath), str(dest))
                moved_count += 1
            except Exception as e:
                print(f"  Warning: could not move {rel}: {e}")

    # 清理空目录
    for root, dirs, files in os.walk(frameworks, topdown=False):
        root_path = Path(root)
        if root_path == frameworks:
            continue
        try:
            if not any(root_path.iterdir()):
                root_path.rmdir()
        except OSError:
            pass

    # 清理 Resources 中指向不存在目标的符号链接
    removed = 0
    for root, dirs, files in os.walk(resources, followlinks=False):
        root_path = Path(root)
        for fname in files:
            fpath = root_path / fname
            if not fpath.is_symlink():
                continue
            try:
                target = fpath.readlink()
                target_abs = (fpath.parent / target).resolve()
                if not target_abs.exists():
                    fpath.unlink()
                    removed += 1
            except OSError:
                # 循环链接或解析失败，直接删除
                try:
                    fpath.unlink()
                    removed += 1
                except OSError:
                    pass

    print(f"Moved {moved_count} non-code files from Frameworks to Resources")
    print(f"Removed {removed} broken symlinks from Resources")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <path-to-app>")
        sys.exit(1)

    app = Path(sys.argv[1])
    if not app.exists():
        print(f"Error: {app} does not exist")
        sys.exit(1)

    fix_bundle(app)
