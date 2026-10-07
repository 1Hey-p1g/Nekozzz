"""Award/finance output only: build a complete immutable plan before Word writes."""

from dataclasses import dataclass
from pathlib import Path

from config.paths import DATA_ROOT, resolve_image_path
from services.word_service import WordService, WordServiceError
from services.word_styles import fallback_styles


class ReportWordPreflightError(ValueError):
    pass


class ReportWordWriteError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReportOutputImage:
    path: Path
    relative_path: str


@dataclass(frozen=True)
class ReportOutputBlock:
    record_id: int
    title: str
    images: tuple[ReportOutputImage, ...]


@dataclass(frozen=True)
class ReportOutputPlan:
    blocks: tuple[ReportOutputBlock, ...]
    insert_title: bool = False

    @property
    def image_count(self):
        return sum(len(block.images) for block in self.blocks)


class ReportWordOutputService:
    def __init__(self, repository, *, data_root=DATA_ROOT, word_factory=None):
        self.repository = repository
        self.data_root = Path(data_root)
        self.word_factory = word_factory or WordService.connect_existing_word

    def build_plan(self, selected_ids, settings, *, insert_title=False):
        if not selected_ids:
            raise ReportWordPreflightError(f'请至少选择一项{self.repository.label}。')
        records, problems = [], []
        for record_id in sorted(set(selected_ids)):
            row = self.repository.get(record_id)
            if row is None:
                problems.append(f'{self.repository.label} ID {record_id} 已不存在')
            else:
                records.append(row)
        records.sort(key=self.repository.order_key)
        blocks = []
        for row in records:
            record_id, title = row[self.repository.key], self.repository.title(row)
            context = f'{title}（ID {record_id}）'
            try:
                pages = self.repository.attachments(record_id)
            except Exception as error:
                problems.append(f'{context}：附件读取失败（{error}）')
                continue
            if not pages:
                problems.append(f'{context}：没有附件')
            images = []
            for page in pages:
                relative = page['路径']
                try:
                    path = resolve_image_path(relative, data_root=self.data_root)
                    if not path.is_file():
                        raise FileNotFoundError(relative)
                except (TypeError, ValueError, OSError):
                    problems.append(f'{context}：缺失或无效图片 {relative!r}')
                    continue
                images.append(ReportOutputImage(path, relative))
            blocks.append(ReportOutputBlock(record_id, title, tuple(images)))
        if problems:
            raise ReportWordPreflightError('输出前检查未通过：\n' + '\n'.join(problems))
        return ReportOutputPlan(tuple(blocks), bool(insert_title))

    def insert(self, selected_ids, settings, *, insert_title=False, confirm_style_fallback=None):
        plan = self.build_plan(selected_ids, settings, insert_title=insert_title)
        word = self.word_factory()
        word.active_document()
        word.selection()
        required = [('图片样式', settings.image_style)]
        if plan.insert_title:
            required.insert(0, ('文本样式', settings.person_name_style))
        fallback = fallback_styles(word, required, confirm_style_fallback, ReportWordPreflightError)
        for block in plan.blocks:
            context = f'{block.title}（ID {block.record_id}）'
            try:
                if plan.insert_title:
                    if settings.person_name_style in fallback:
                        word.set_selection_style(use_normal=True)
                    else:
                        word.set_selection_style(settings.person_name_style)
                    word.insert_text(block.title)
                    word.insert_paragraph()
                if settings.image_style in fallback:
                    word.set_selection_style(use_normal=True)
                else:
                    word.set_selection_style(settings.image_style)
                for image in block.images:
                    context = f'{block.title} / {image.relative_path}'
                    word.insert_inline_image(image.path, shrink_oversized=settings.shrink_oversized_images,
                                             enlarge_small=settings.enlarge_small_images)
                word.insert_page_break()
            except WordServiceError as error:
                raise ReportWordWriteError(f'Word 插入未完整完成，失败位置：{context}；请检查当前 Word 文档。') from error
        return plan
