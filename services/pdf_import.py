"""Render complete PDFs to ordered temporary JPEGs; never retain the PDF."""

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QTransform

from services.settings import PdfSettings
from config.paths import DATA_ROOT


@dataclass(frozen=True)
class RenderedPage:
    number: int
    path: Path


@contextmanager
def render_pdf(source_path, settings=None):
    """Yield every page in PDF order; remove all temporary files on exit/error."""
    settings = (settings or PdfSettings()).validate()
    source = Path(source_path)
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise ValueError(f"请选择有效的 PDF 文件：{source}")
    if source.resolve() == DATA_ROOT.resolve() or DATA_ROOT.resolve() in source.resolve().parents:
        raise ValueError("请选择 TenderSystem 项目目录外的 PDF 原件")
    with TemporaryDirectory(prefix="TenderSystem_pdf_") as directory:
        pages = []
        with pymupdf.open(str(source)) as document:
            if document.needs_pass:
                raise ValueError("暂不支持加密 PDF")
            if document.page_count == 0:
                raise ValueError("PDF 没有页面")
            colorspace = pymupdf.csRGB if settings.color_mode == "RGB" else pymupdf.csGRAY
            for number, page in enumerate(document, 1):
                pixmap = page.get_pixmap(dpi=settings.dpi, colorspace=colorspace, alpha=False)
                destination = Path(directory) / f"{number:06d}.jpg"
                destination.write_bytes(pixmap.tobytes("jpeg", jpg_quality=settings.jpeg_quality))
                pages.append(RenderedPage(number, destination))
        yield tuple(pages)


def rotate_temporary_page(page, degrees, *, quality=90):
    """Rotate one rendered page on user request, preserving all other pages."""
    if degrees not in (-90, 90):
        raise ValueError("只能旋转 90°")
    image = QImage(str(page.path))
    if image.isNull():
        raise ValueError(f"无法读取第 {page.number} 页 JPEG")
    rotated = image.transformed(QTransform().rotate(degrees), Qt.SmoothTransformation)
    if not rotated.save(str(page.path), "JPEG", quality):
        raise OSError(f"无法保存第 {page.number} 页的旋转结果")
