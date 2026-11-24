#!/usr/bin/env python3
"""Render the TandOrbit SVG artwork to the formats used by the desktop clients."""

from __future__ import annotations

import os
import struct
from io import BytesIO
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

RESOURCES = Path(__file__).resolve().parents[1] / "resources"


def render(source: Path, size: int) -> QImage:
    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise ValueError(f"Invalid SVG: {source}")
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    view = renderer.viewBoxF()
    scale = min(size / view.width(), size / view.height())
    width, height = view.width() * scale, view.height() * scale
    renderer.render(painter, QRectF((size - width) / 2, (size - height) / 2, width, height))
    painter.end()
    return image


def write_png(image: QImage, path: Path) -> None:
    if not image.save(str(path), "PNG"):
        raise OSError(f"Could not write {path}")


def png_bytes(image: QImage) -> bytes:
    target = QBuffer()
    target.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(target, "PNG"):
        raise OSError("Could not encode PNG icon frame")
    return bytes(target.data())


def write_ico(source: Path, destination: Path) -> None:
    sizes = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
    frames = [png_bytes(render(source, size)) for size in sizes]
    data = BytesIO()
    data.write(struct.pack("<HHH", 0, 1, len(frames)))
    offset = 6 + 16 * len(frames)
    for size, frame in zip(sizes, frames):
        dimension = size % 256
        data.write(struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(frame), offset))
        offset += len(frame)
    for frame in frames:
        data.write(frame)
    destination.write_bytes(data.getvalue())


def write_icns(source: Path, destination: Path) -> None:
    types = {
        b"icp4": 16, b"icp5": 32, b"icp6": 64, b"ic07": 128, b"ic08": 256,
        b"ic09": 512, b"ic10": 1024, b"ic11": 32, b"ic12": 64,
        b"ic13": 256, b"ic14": 512,
    }
    frames = {size: png_bytes(render(source, size)) for size in sorted(set(types.values()))}
    chunks = b"".join(
        struct.pack(">4sI", kind, len(frames[size]) + 8) + frames[size]
        for kind, size in types.items()
    )
    destination.write_bytes(struct.pack(">4sI", b"icns", len(chunks) + 8) + chunks)


def main() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication([])
    source = RESOURCES / "icon.svg"
    write_png(render(source, 512), RESOURCES / "icon.png")
    write_ico(source, RESOURCES / "icon.ico")
    for suffix, size in (("", 18), ("@2x", 36)):
        write_png(render(RESOURCES / "tray_icon.svg", size), RESOURCES / f"tray_icon{suffix}.png")
    write_icns(source, RESOURCES / "icon.icns")
    app.quit()


if __name__ == "__main__":
    main()
