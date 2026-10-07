from services.word_styles import fallback_styles
"""In-memory multi-person Word task, complete preflight, and ordered output."""

from dataclasses import dataclass, field
from pathlib import Path
import sqlite3

from config.paths import DATA_ROOT, resolve_image_path
from services.word_service import WordService, WordServiceError


@dataclass
class PersonWordItem:
    person_id: int
    selected_certificate_ids: set[int] = field(default_factory=set)


@dataclass
class PersonWordJob:
    persons: list[PersonWordItem] = field(default_factory=list)
    insert_person_name: bool = False

    def add(self, person_id):
        if any(item.person_id == person_id for item in self.persons):
            return False
        self.persons.append(PersonWordItem(person_id))
        return True

    def remove(self, person_id):
        self.persons = [item for item in self.persons if item.person_id != person_id]

    def item(self, person_id):
        return next((item for item in self.persons if item.person_id == person_id), None)

    def reorder(self, person_ids):
        ids = [item.person_id for item in self.persons]
        if len(person_ids) != len(ids) or set(person_ids) != set(ids):
            raise ValueError("人员输出顺序与任务人员不一致")
        by_id = {item.person_id: item for item in self.persons}
        self.persons = [by_id[person_id] for person_id in person_ids]


@dataclass(frozen=True)
class OutputImage:
    path: Path
    relative_path: str
    certificate_name: str
    certificate_id: int


@dataclass(frozen=True)
class PersonOutputBlock:
    person_id: int
    person_name: str
    images: tuple[OutputImage, ...]
    certificate_count: int


@dataclass(frozen=True)
class PersonWordOutputPlan:
    blocks: tuple[PersonOutputBlock, ...]
    insert_person_name: bool

    @property
    def image_count(self):
        return sum(len(block.images) for block in self.blocks)


class PersonWordPreflightError(Exception):
    pass


class PersonWordWriteError(Exception):
    pass


class PersonWordOutputService:
    def __init__(self, people_service, *, data_root=DATA_ROOT, word_factory=None):
        self.people = people_service.people
        self.certificates = people_service.certificates
        self.data_root = Path(data_root)
        self.word_factory = word_factory or WordService.connect_existing_word

    @staticmethod
    def insert_images(word, images, settings, *, before_image=None, after_image=None):
        """Shared continuous image primitive; caller owns names and pagination."""
        for image in images:
            if before_image:
                before_image(image)
            word.insert_inline_image(
                image.path,
                shrink_oversized=settings.shrink_oversized_images,
                enlarge_small=settings.enlarge_small_images,
            )
            if after_image:
                after_image(image)

    def build_plan(self, job, settings):
        """Read and validate all source data before connecting to Word."""
        if not job.persons:
            raise PersonWordPreflightError("请先添加至少一名人员。")
        rank = {name.strip(): index for index, name in enumerate(settings.person_certificate_type_order)}
        problems = []
        missing_images = 0
        blocks = []
        for item in job.persons:
            try:
                person = self.people.get(item.person_id)
            except sqlite3.Error as error:
                problems.append(f"人员 ID {item.person_id}：读取人员资料失败（{error}）")
                continue
            if person is None:
                problems.append(f"人员 ID {item.person_id} 已不存在")
                continue
            name = person["姓名"]
            if not item.selected_certificate_ids:
                problems.append(f"{name}：尚未选择证书")
                continue
            chosen = []
            for certificate_id in item.selected_certificate_ids:
                try:
                    certificate = self.certificates.get(certificate_id)
                except sqlite3.Error as error:
                    problems.append(f"{name}：读取证书 ID {certificate_id} 失败（{error}）")
                    continue
                if certificate is None or certificate["人员ID"] != item.person_id:
                    problems.append(f"{name}：证书 ID {certificate_id} 已不存在或不属于该人员")
                else:
                    chosen.append(certificate)
            chosen.sort(key=lambda cert: (
                rank.get((cert["证书类型"] or "").strip(), len(rank)),
                (cert["证书类型"] or "").strip() if (cert["证书类型"] or "").strip() not in rank else "",
                cert["证书ID"],
            ))
            images = []
            for certificate in chosen:
                cert_name = certificate["证书名称"]
                try:
                    pages = self.certificates.attachments(certificate["证书ID"])
                except sqlite3.Error as error:
                    problems.append(f"{name} / {cert_name}：读取附件失败（{error}）")
                    continue
                if not pages:
                    problems.append(f"{name} / {cert_name}（ID {certificate['证书ID']}）：没有附件")
                for page in pages:
                    relative = page["路径"]
                    try:
                        path = resolve_image_path(relative, data_root=self.data_root)
                    except (TypeError, ValueError):
                        missing_images += 1
                        problems.append(f"{name} / {cert_name}：无效图片路径 {relative!r}")
                        continue
                    if not path.is_file():
                        missing_images += 1
                        problems.append(f"{name} / {cert_name}：图片不存在 {relative}")
                    images.append(OutputImage(path, relative, cert_name, certificate["证书ID"]))
            blocks.append(PersonOutputBlock(item.person_id, name, tuple(images), len(chosen)))
        if problems:
            image_summary = f"缺失或无效图片 {missing_images} 张；" if missing_images else ""
            raise PersonWordPreflightError(
                f"输出前检查未通过（{image_summary}共 {len(problems)} 项）：\n" + "\n".join(problems)
            )
        return PersonWordOutputPlan(tuple(blocks), job.insert_person_name)

    def insert(self, job, settings, *, confirm_style_fallback=None):
        plan = self.build_plan(job, settings)
        word = self.word_factory()
        word.active_document()
        word.selection()
        labeled = ([('文本样式', settings.person_name_style)] if plan.insert_person_name else [])
        labeled.append(('图片样式', settings.image_style))
        fallback = fallback_styles(word, labeled, confirm_style_fallback, PersonWordPreflightError)
        for block in plan.blocks:
            context = block.person_name
            try:
                if plan.insert_person_name:
                    word.set_selection_style(use_normal=True) if settings.person_name_style in fallback else word.set_selection_style(settings.person_name_style)
                    word.insert_text(block.person_name)
                    word.insert_paragraph()
                word.set_selection_style(use_normal=True) if settings.image_style in fallback else word.set_selection_style(settings.image_style)
                def track_image(image):
                    nonlocal context
                    context = f"{block.person_name} / {image.certificate_name}（ID {image.certificate_id}）"
                self.insert_images(word, block.images, settings, before_image=track_image)
                context = block.person_name
                word.insert_page_break()
            except WordServiceError as error:
                raise PersonWordWriteError(f"Word 插入未完整完成，失败位置：{context}；请检查当前 Word 文档。") from error
        return plan
