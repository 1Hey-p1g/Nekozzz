"""Certificate PDF page publication with SQLite rollback and file cleanup."""

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QImage

from config.paths import DATA_ROOT, resolve_image_path
from database.runtime import runtime_connection
from repositories.attachment_repository import (
    CertificateAttachmentRepository, ProjectAttachmentRepository, QualificationAttachmentRepository,
    AwardAttachmentRepository, FinanceAttachmentRepository,
)


@dataclass(frozen=True)
class AttachmentResult:
    page_count: int
    old_files_not_removed: tuple[str, ...] = ()


class CertificateAttachmentService:
    parent_name = '证书'

    def __init__(self, database_path, *, data_root=DATA_ROOT):
        self.database_path = database_path
        self.data_root = Path(data_root)
        self.repository = CertificateAttachmentRepository()

    def save_pages(self, certificate_id, pages, *, replace=False):
        """Publish a complete ordered PDF; never touch old files before commit."""
        pages = tuple(pages)
        if not pages or [page.number for page in pages] != list(range(1, len(pages) + 1)):
            raise ValueError("PDF 页面必须从 1 开始连续编号")
        for page in pages:
            if not page.path.is_file() or QImage(str(page.path)).isNull():
                raise ValueError(f"第 {page.number} 页 JPEG 无法读取")
        images = self.data_root / "Images"
        images.mkdir(parents=True, exist_ok=True)
        created = []
        try:
            entries = []
            for page in pages:
                # Exclusive create protects existing and legacy filenames even on UUID collision.
                while True:
                    relative = f"Images/{uuid.uuid4()}.jpg"
                    destination = images / relative.removeprefix("Images/")
                    try:
                        with destination.open("xb") as output:
                            created.append(destination)
                            with page.path.open("rb") as source:
                                shutil.copyfileobj(source, output)
                        break
                    except FileExistsError:
                        continue
                entries.append((page.number, relative))
            with runtime_connection(self.database_path, write=True) as connection:
                connection.execute("BEGIN IMMEDIATE")
                if not self.repository.parent_exists(connection, certificate_id):
                    raise LookupError(f"{self.parent_name} ID {certificate_id} 不存在")
                old_paths = self.repository.paths(connection, certificate_id)
                if bool(old_paths) != replace:
                    raise ValueError("已有附件时请使用整份替换；无附件时请使用导入")
                self.repository.replace_rows(connection, certificate_id, entries)
        except BaseException:
            for path in created:
                path.unlink(missing_ok=True)
            raise
        return AttachmentResult(len(pages), self._cleanup_old(old_paths))

    def delete_all(self, certificate_id):
        with runtime_connection(self.database_path, write=True) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if not self.repository.parent_exists(connection, certificate_id):
                raise LookupError(f"{self.parent_name} ID {certificate_id} 不存在")
            old_paths = self.repository.paths(connection, certificate_id)
            self.repository.delete_rows(connection, certificate_id)
        return AttachmentResult(len(old_paths), self._cleanup_old(old_paths))

    def _cleanup_old(self, paths):
        retained = []
        with runtime_connection(self.database_path) as connection:
            for relative in dict.fromkeys(paths):
                try:
                    if self.repository.still_referenced(connection, relative, data_root=self.data_root):
                        continue
                    resolve_image_path(relative, data_root=self.data_root).unlink(missing_ok=True)
                except (OSError, TypeError, ValueError):
                    retained.append(relative)
        return tuple(retained)


class ProjectAttachmentService(CertificateAttachmentService):
    """Reuse JPEG publication/rollback for a (project ID, file type) group."""

    def __init__(self, database_path, *, data_root=DATA_ROOT):
        super().__init__(database_path, data_root=data_root)
        self.repository = ProjectAttachmentRepository()


class QualificationAttachmentService(CertificateAttachmentService):
    """Reuse the publisher and shared-path cleanup for qualification groups."""

    parent_name = '公司资质'

    def __init__(self, database_path, *, data_root=DATA_ROOT):
        super().__init__(database_path, data_root=data_root)
        self.repository = QualificationAttachmentRepository()


class AwardAttachmentService(CertificateAttachmentService):
    parent_name = '获奖工程'

    def __init__(self, database_path, *, data_root=DATA_ROOT):
        super().__init__(database_path, data_root=data_root)
        self.repository = AwardAttachmentRepository()


class FinanceAttachmentService(CertificateAttachmentService):
    parent_name = '财务报告'

    def __init__(self, database_path, *, data_root=DATA_ROOT):
        super().__init__(database_path, data_root=data_root)
        self.repository = FinanceAttachmentRepository()
