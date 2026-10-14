"""Portable application preferences, separate from business data."""

import json
import os
import tempfile
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

from config.paths import SETTINGS_FILE


@dataclass(frozen=True)
class PdfSettings:
    dpi: int = 200
    jpeg_quality: int = 90
    color_mode: str = "RGB"
    image_style: str = "图片"
    person_name_style: str = "标题 4"
    shrink_oversized_images: bool = True
    enlarge_small_images: bool = False
    # Future Word ordering: configured type rank, then 证书ID ASC; images retain page order.
    person_certificate_type_order: tuple[str, ...] = ()
    project_attachment_type_order: tuple[str, ...] = ()
    company_qualification_name_order: tuple[str, ...] = ()
    theme: str = 'system'
    # Empty means built-in Normal (resolved by Word ID, never a localized name).
    autofill_title_style: str = ''
    autofill_note_style: str = ''
    autofill_person_name_style: str = ''
    writer_target: str = 'word'
    window_geometry: str = ''

    def normalized(self):
        if not isinstance(self.image_style, str) or not isinstance(self.person_name_style, str):
            raise ValueError("Word 样式名称必须为文本")
        if any(not isinstance(name, str) for name in (
                self.autofill_title_style, self.autofill_note_style,
                self.autofill_person_name_style)):
            raise ValueError("自动填表样式名称必须为文本")
        order = self.person_certificate_type_order
        if not isinstance(order, (list, tuple)) or any(not isinstance(item, str) for item in order):
            raise ValueError("证书类型顺序必须为文本列表")
        project_order = self.project_attachment_type_order
        if not isinstance(project_order, (list, tuple)) or any(not isinstance(item, str) for item in project_order):
            raise ValueError("工程附件类型顺序必须为文本列表")
        qualification_order = self.company_qualification_name_order
        if not isinstance(qualification_order, (list, tuple)) or any(not isinstance(item, str) for item in qualification_order):
            raise ValueError("公司资质名称顺序必须为文本列表")
        return replace(
            self,
            window_geometry=self.window_geometry if isinstance(self.window_geometry, str) and len(self.window_geometry) <= 16384 else '',
            image_style=self.image_style.strip() or "图片",
            person_name_style=self.person_name_style.strip() or "标题 4",
            autofill_title_style=self.autofill_title_style.strip(),
            autofill_note_style=self.autofill_note_style.strip(),
            autofill_person_name_style=self.autofill_person_name_style.strip(),
            person_certificate_type_order=tuple(dict.fromkeys(
                item.strip() for item in order if item.strip()
            )),
            project_attachment_type_order=tuple(dict.fromkeys(
                item.strip() for item in project_order if item.strip()
            )),
            company_qualification_name_order=tuple(dict.fromkeys(
                item.strip() for item in qualification_order if item.strip()
            )),
        )

    def validate(self):
        if self.writer_target not in ('word', 'wps'):
            raise ValueError('文档插入目标必须为 Microsoft Word 或 WPS Writer')
        if self.theme not in ('system', 'light', 'dark'):
            raise ValueError('Theme must be system, light or dark')
        if type(self.dpi) is not int or self.dpi not in (150, 200, 300):
            raise ValueError("PDF DPI 必须为 150、200 或 300")
        if type(self.jpeg_quality) is not int or self.jpeg_quality not in (70, 85, 90, 100):
            raise ValueError("JPEG Quality 必须为 70、85、90 或 100")
        if self.color_mode not in ("RGB", "Grayscale"):
            raise ValueError("颜色模式必须为 RGB 或 Grayscale")
        if type(self.shrink_oversized_images) is not bool or type(self.enlarge_small_images) is not bool:
            raise ValueError("图片尺寸设置必须为布尔值")
        return self


def merge_certificate_type_order(saved_order, database_types):
    """Keep saved (including currently absent) types, then append new types predictably."""
    saved = tuple(dict.fromkeys(item.strip() for item in saved_order if item and item.strip()))
    discovered = sorted({item.strip() for item in database_types if item and item.strip()})
    return saved + tuple(item for item in discovered if item not in saved)


class SettingsService:
    def __init__(self, path=SETTINGS_FILE):
        self.path = Path(path)

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return PdfSettings()
            defaults = PdfSettings()
            known = {field.name: data.get(field.name, getattr(defaults, field.name)) for field in fields(PdfSettings)}
            return PdfSettings(**known).normalized().validate()
        except (OSError, ValueError, TypeError):
            return PdfSettings()

    def save(self, settings):
        settings = settings.normalized().validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            existing = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = {}
        if not isinstance(existing, dict):
            existing = {}
        existing.update(asdict(settings))
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent,
                                             prefix=".settings-", suffix=".tmp", delete=False) as output:
                temporary = Path(output.name)
                json.dump(existing, output, ensure_ascii=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
