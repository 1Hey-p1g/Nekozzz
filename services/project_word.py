from services.word_styles import fallback_styles
"""Engineering task → immutable plan → strict preflight → frozen Word primitives."""

from dataclasses import dataclass, field
from pathlib import Path
import sqlite3

from config.paths import DATA_ROOT, resolve_image_path
from services.word_service import WordService, WordServiceError


@dataclass
class ProjectWordItem:
    project_id: int
    selected_attachment_types: set[str] = field(default_factory=set)


@dataclass
class ProjectWordJob:
    projects: list[ProjectWordItem] = field(default_factory=list)
    insert_project_name: bool = False

    def item(self, project_id):
        return next((item for item in self.projects if item.project_id == project_id), None)

    def add(self, project_id):
        if self.item(project_id) is not None:
            return False
        self.projects.append(ProjectWordItem(project_id))
        return True

    def remove(self, project_id):
        self.projects = [item for item in self.projects if item.project_id != project_id]

    def reorder(self, ids):
        if len(ids) != len(self.projects) or set(ids) != {item.project_id for item in self.projects}:
            raise ValueError('工程顺序与任务不一致')
        values = {item.project_id: item for item in self.projects}
        self.projects = [values[value] for value in ids]


@dataclass(frozen=True)
class ProjectOutputImage:
    path: Path
    file_type: str
    relative_path: str


@dataclass(frozen=True)
class ProjectOutputBlock:
    project_id: int
    project_name: str
    images: tuple[ProjectOutputImage, ...]


@dataclass(frozen=True)
class ProjectWordOutputPlan:
    blocks: tuple[ProjectOutputBlock, ...]
    insert_project_name: bool

    @property
    def image_count(self):
        return sum(len(block.images) for block in self.blocks)


class ProjectWordPreflightError(Exception):
    pass


class ProjectWordWriteError(Exception):
    pass


class ProjectWordOutputService:
    def __init__(self, repository, *, data_root=DATA_ROOT, word_factory=None):
        self.projects = repository
        self.data_root = Path(data_root)
        self.word_factory = word_factory or WordService.connect_existing_word

    def build_plan(self, job, settings):
        if not job.projects:
            raise ProjectWordPreflightError('请先添加至少一项工程。')
        rank = {value.strip(): i for i, value in enumerate(settings.project_attachment_type_order)}
        problems, blocks = [], []
        missing_count = 0
        for item in job.projects:
            try:
                project = self.projects.get(item.project_id)
            except sqlite3.Error as error:
                problems.append(f'工程 ID {item.project_id}：读取失败（{error}）')
                continue
            if project is None:
                problems.append(f'工程 ID {item.project_id} 已不存在')
                continue
            name = project['项目名称']
            if not item.selected_attachment_types:
                problems.append(f'{name}：尚未选择附件类型')
                continue
            images = []
            types = sorted(item.selected_attachment_types, key=lambda value: (
                rank.get(value.strip(), len(rank)), value.strip() if value.strip() not in rank else '', value))
            for file_type in types:
                try:
                    pages = self.projects.attachments(item.project_id, file_type)
                except sqlite3.Error as error:
                    problems.append(f'{name} / {file_type}：附件读取失败（{error}）')
                    continue
                if not pages:
                    problems.append(f'{name} / {file_type}：文件类型已不存在或没有附件')
                for page in pages:
                    relative = page['路径']
                    try:
                        path = resolve_image_path(relative, data_root=self.data_root)
                        if not path.is_file():
                            raise FileNotFoundError(relative)
                    except (ValueError, TypeError, OSError):
                        missing_count += 1
                        problems.append(f'{name} / {file_type}：缺失或无效图片 {relative!r}')
                        continue
                    images.append(ProjectOutputImage(path, file_type, relative))
            blocks.append(ProjectOutputBlock(item.project_id, name, tuple(images)))
        if problems:
            raise ProjectWordPreflightError(f'输出前检查未通过（缺失或无效图片 {missing_count} 张）：\n' + '\n'.join(problems))
        return ProjectWordOutputPlan(tuple(blocks), job.insert_project_name)

    def insert(self, job, settings, *, confirm_style_fallback=None):
        plan = self.build_plan(job, settings)
        word = self.word_factory()
        word.active_document()
        word.selection()
        labeled = ([('文本样式', settings.person_name_style)] if plan.insert_project_name else [])
        labeled.append(('图片样式', settings.image_style))
        fallback = fallback_styles(word, labeled, confirm_style_fallback, ProjectWordPreflightError)
        for block in plan.blocks:
            context = block.project_name
            try:
                if plan.insert_project_name:
                    word.set_selection_style(use_normal=True) if settings.person_name_style in fallback else word.set_selection_style(settings.person_name_style)
                    word.insert_text(block.project_name)
                    word.insert_paragraph()
                word.set_selection_style(use_normal=True) if settings.image_style in fallback else word.set_selection_style(settings.image_style)
                for image in block.images:
                    context = f'{block.project_name} / {image.file_type} / {image.relative_path}'
                    word.insert_inline_image(image.path, shrink_oversized=settings.shrink_oversized_images,
                                             enlarge_small=settings.enlarge_small_images)
                context = block.project_name
                word.insert_page_break()
            except WordServiceError as error:
                raise ProjectWordWriteError(f'Word 插入未完整完成，失败位置：{context}；请检查当前 Word 文档。') from error
        return plan
