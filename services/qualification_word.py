"""Read-only qualification output plan, complete preflight, then Word primitives."""

from dataclasses import dataclass
from pathlib import Path

from config.paths import DATA_ROOT, resolve_image_path
from services.word_service import WordService, WordServiceError
from services.word_styles import fallback_styles


class QualificationWordPreflightError(ValueError):
    pass


class QualificationWordWriteError(RuntimeError):
    pass


@dataclass(frozen=True)
class QualificationOutputImage:
    path: Path
    relative_path: str


@dataclass(frozen=True)
class QualificationOutputBlock:
    qualification_id: int
    name: str
    images: tuple[QualificationOutputImage, ...]


@dataclass(frozen=True)
class QualificationOutputPlan:
    blocks: tuple[QualificationOutputBlock, ...]
    insert_qualification_name: bool = False

    @property
    def image_count(self):
        return sum(len(block.images) for block in self.blocks)


class QualificationWordOutputService:
    def __init__(self, repository, *, data_root=DATA_ROOT, word_factory=None):
        self.repository = repository
        self.data_root = Path(data_root)
        self.word_factory = word_factory or WordService.connect_existing_word

    def build_plan(self, selected_ids, settings, *, insert_qualification_name=False):
        ids = set(selected_ids)
        if not ids:
            raise QualificationWordPreflightError('请至少选择一项公司资质。')
        records, problems = [], []
        for qualification_id in sorted(ids):
            row = self.repository.get(qualification_id)
            if row is None:
                problems.append(f'资质 ID {qualification_id} 已不存在')
            else:
                records.append(row)
        order = {name: i for i, name in enumerate(settings.company_qualification_name_order)}
        records.sort(key=lambda row: (
            order.get(row['资质证书名称'].strip(), len(order)),
            '' if row['资质证书名称'].strip() in order else row['资质证书名称'].strip(), row['资质ID']))
        blocks = []
        for row in records:
            qualification_id, name = row['资质ID'], row['资质证书名称']
            context = f"{row['公司名称']} / {name}（ID {qualification_id}）"
            try:
                pages = self.repository.attachments(qualification_id)
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
                images.append(QualificationOutputImage(path, relative))
            blocks.append(QualificationOutputBlock(qualification_id, name, tuple(images)))
        if problems:
            raise QualificationWordPreflightError('输出前检查未通过：\n' + '\n'.join(problems))
        return QualificationOutputPlan(tuple(blocks), insert_qualification_name)

    def insert(self, selected_ids, settings, *, insert_qualification_name=False, confirm_style_fallback=None):
        plan = self.build_plan(selected_ids, settings, insert_qualification_name=insert_qualification_name)
        word = self.word_factory()
        word.active_document()
        word.selection()
        required = [('图片样式', settings.image_style)]
        if plan.insert_qualification_name:
            required.insert(0, ('文本样式', settings.person_name_style))
        fallback = fallback_styles(word, required,
                                   confirm_style_fallback, QualificationWordPreflightError)
        for block in plan.blocks:
            context = f'{block.name}（ID {block.qualification_id}）'
            try:
                if plan.insert_qualification_name:
                    if settings.person_name_style in fallback:
                        word.set_selection_style(use_normal=True)
                    else:
                        word.set_selection_style(settings.person_name_style)
                    word.insert_text(block.name)
                    word.insert_paragraph()
                if settings.image_style in fallback:
                    word.set_selection_style(use_normal=True)
                else:
                    word.set_selection_style(settings.image_style)
                for image in block.images:
                    context = f'{block.name} / {image.relative_path}'
                    word.insert_inline_image(image.path,
                        shrink_oversized=settings.shrink_oversized_images,
                        enlarge_small=settings.enlarge_small_images)
                word.insert_page_break()
            except WordServiceError as error:
                raise QualificationWordWriteError(
                    f'Word 插入未完整完成，失败位置：{context}；请检查当前 Word 文档。') from error
        return plan
