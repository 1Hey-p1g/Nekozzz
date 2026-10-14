"""Read-only personnel mapping, existing attachment preflight, immutable plan."""
from copy import deepcopy
from dataclasses import dataclass
from io import BytesIO
from zipfile import ZipFile
from types import SimpleNamespace
import sqlite3
from zipfile import BadZipFile

from config.paths import DATA_ROOT
from services.people import age_from_identity, gender_from_identity
from services.person_word import PersonWordJob, PersonWordItem, PersonWordOutputService, OutputImage
from services.word_service import WordService
from services.word_styles import fallback_styles
from . import template_core as core
from .table_xml import freeze_inherited_format, flat_package, ending_paragraph, fit_table_to_available_width


class AutoFillPreflightError(ValueError):
    pass


class AutoFillWriteError(RuntimeError):
    pass


@dataclass(frozen=True)
class AutoFillBlock:
    number: int
    person_ids: tuple[int, ...]
    table: bytes
    images_by_person: tuple[tuple[OutputImage, ...], ...]
    person_names: tuple[str, ...]


@dataclass(frozen=True)
class AutoFillPlan:
    blocks: tuple[AutoFillBlock, ...]
    title: str
    note: str
    shrink_wide_tables: bool

    @property
    def image_count(self):
        return sum(len(images) for b in self.blocks for images in b.images_by_person)


def value(raw):
    return str(raw).strip() if raw is not None and str(raw).strip() else '/'


def format_project_experience(project_name, role):
    """Keep the existing missing-name policy; omit absent roles entirely."""
    name = value(project_name)
    role_text = str(role).strip() if role is not None else ''
    return f'{name}（{role_text}）' if role_text else name


def professional_titles(certificates):
    """Exact type, repository order, nonempty distinct names; no selection inference."""
    names = dict.fromkeys(
        str(c['证书名称']).strip() for c in certificates
        if c['证书类型'] == '职称证' and c['证书名称'] is not None
        and str(c['证书名称']).strip()
    )
    return '\n'.join(names) or '/'


class PersonAutoFillService:
    def __init__(self, people_service, *, data_root=DATA_ROOT, word_factory=None, cursor_factory=None):
        self.people_service = people_service
        self.attachments = PersonWordOutputService(people_service, data_root=data_root)
        self.word_factory = word_factory or WordService.connect_existing_word
        if cursor_factory is None:
            from .word_cursor import WordTableCursor
            cursor_factory = WordTableCursor
        self.cursor_factory = cursor_factory

    def certificates(self, person_id, *, document_order=False):
        return self.people_service.certificates.for_person(person_id, document_order=document_order)

    def projects(self, person_id, *, document_order=False):
        return self.people_service.people.projects(person_id, document_order=document_order)

    def build_plan(self, task, settings):
        try:
            return self._build_plan(task, settings)
        except (sqlite3.Error, OSError, BadZipFile) as error:
            raise AutoFillPreflightError(f'自动填表数据预检查失败：{error}') from error

    def _build_plan(self, task, settings):
        if not task.people:
            raise AutoFillPreflightError('请先添加人员。')
        if len({p.person_id for p in task.people}) != len(task.people):
            raise AutoFillPreflightError('任务有重复人员。')
        source, _, _, template = core.load_template(task.template_path)
        with ZipFile(BytesIO(source)) as archive:
            styles = archive.read('word/styles.xml')
        records, certificates, rows = {}, {}, []
        for entry in task.people:
            person = self.people_service.people.get(entry.person_id)
            if not person or value(person['姓名']) == '/':
                raise AutoFillPreflightError(f'人员 {entry.person_id} 不存在或姓名为空')
            records[entry.person_id] = person
            certs = {c['证书ID']: c for c in self.certificates(entry.person_id, document_order=True)}
            certificates.update(certs)
            for chosen in (entry.table_certificate_ids, entry.attachment_certificate_ids):
                if not chosen <= certs.keys():
                    raise AutoFillPreflightError(f"{person['姓名']}：选择的证书不存在或不属于此人员")
            projects = self.projects(entry.person_id, document_order=True)
            if not entry.table_project_ids <= {p['ID'] for p in projects}:
                raise AutoFillPreflightError(f"{person['姓名']}：选择的业绩不存在或不属于此人员")
            cert_text = '\n'.join(' '.join(str(v).strip() for v in (certs[i]['证书名称'] or certs[i]['证书类型'], certs[i]['证书编号']) if v is not None and str(v).strip()) or '/' for i in sorted(entry.table_certificate_ids))
            project_text = '\n'.join(format_project_experience(p['项目名称'], p['担任角色']) for p in projects if p['ID'] in entry.table_project_ids)
            rows.append(core.PersonTableData(
                person['姓名'], value(gender_from_identity(person['身份证号'])), value(age_from_identity(person['身份证号'])),
                value(person['毕业院校']), value(person['专业']), professional_titles(certs.values()),
                value(cert_text), value(entry.role_text), value(project_text)))
        # Cached read facade lets the accepted attachment builder reuse this task's
        # prefetch. Attachment page/path ordering and validation are not reimplemented.
        cached = SimpleNamespace(
            people=SimpleNamespace(get=records.get),
            certificates=SimpleNamespace(get=certificates.get, attachments=self.people_service.certificates.attachments))
        selected = [PersonWordItem(p.person_id, set(p.attachment_certificate_ids)) for p in task.people if p.attachment_certificate_ids]
        image_map = {}
        if selected:
            reused = PersonWordOutputService(cached, data_root=self.attachments.data_root)
            image_map = {b.person_id: b.images for b in reused.build_plan(PersonWordJob(selected), settings).blocks}
        blocks = []
        for offset in range(0, len(rows), core.CAPACITY):
            table = deepcopy(template)
            for slot in core.BLOCKS:
                row = rows[offset+slot.slot] if offset+slot.slot < len(rows) else None
                for field, address in slot.targets().items():
                    core.replace_target_text_preserving_format(core.cell_at(table, address), str(getattr(row, field)) if row else '/')
            table = freeze_inherited_format(table, styles)
            ids = tuple(p.person_id for p in task.people[offset:offset+core.CAPACITY])
            # Construct/parse every package now, before any Word connection/mutation.
            core.parse_xml(flat_package([table, ending_paragraph()]).encode())
            blocks.append(AutoFillBlock(len(blocks)+1, ids, core.etree.tostring(table),
                                        tuple(image_map.get(i, ()) for i in ids),
                                        tuple(records[i]['姓名'] for i in ids)))
        return AutoFillPlan(tuple(blocks), task.title_text if task.include_title else '', task.note_text if task.include_note else '', task.shrink_wide_tables)

    def insert(self, task, settings, *, confirm_style_fallback=None):
        plan = self.build_plan(task, settings)
        word = self.word_factory()
        cursor = self.cursor_factory(word)  # Validate body/collapsed/table/editability first.
        usable_width = cursor.available_width()
        tables = [fit_table_to_available_width(core.parse_xml(b.table), usable_width) if plan.shrink_wide_tables else core.parse_xml(b.table) for b in plan.blocks]
        packages = [flat_package([t, ending_paragraph()]) for t in tables]
        required = []
        if plan.title:
            required.append(('自动填表表头', settings.autofill_title_style))
        if plan.note:
            required.append(('自动填表注释', settings.autofill_note_style))
        required.append(('自动填表人员姓名', settings.autofill_person_name_style))
        if plan.image_count:
            required.append(('图片样式', settings.image_style))
        fallback = fallback_styles(word, [(label, name) for label, name in required if name],
                                   confirm_style_fallback, AutoFillPreflightError)
        # Empty AutoFill preferences resolve by built-in Normal ID; custom names
        # get the shared, per-operation fallback. Resolve all before mutation.
        for _, name in required:
            word.resolve_style(name, use_normal=not name or name in fallback)
        cursor.assert_unchanged()
        completed = []
        for block, xml in zip(plan.blocks, packages):
            stage, person_index = '标题', None
            completed_stages, completed_images = [], 0
            try:
                cursor.boundary()
                if plan.title:
                    cursor.text(plan.title, settings.autofill_title_style,
                                not settings.autofill_title_style or settings.autofill_title_style in fallback)
                    completed_stages.append('标题')
                stage = '表格'
                cursor.table(xml)
                completed_stages.append('表格')
                if plan.note:
                    stage = '注释'
                    cursor.text(plan.note, settings.autofill_note_style,
                                not settings.autofill_note_style or settings.autofill_note_style in fallback)
                    completed_stages.append('注释')
                attachment_position = cursor.position
                cursor.attachment_start(attachment_position)
                for person_index, images in enumerate(block.images_by_person, 1):
                    stage = f'人员 {person_index} 姓名'
                    # End a preceding image paragraph only when needed. text()
                    # creates the independent name paragraph and advances anchor.
                    cursor.boundary()
                    cursor.text(block.person_names[person_index-1], settings.autofill_person_name_style,
                                not settings.autofill_person_name_style or settings.autofill_person_name_style in fallback)
                    completed_stages.append(f'人员 {person_index} 姓名')
                    if images:
                        cursor.image_style(settings.image_style, settings.image_style in fallback)
                    stage = f'人员 {person_index} 附件'
                    def before_image(image):
                        nonlocal stage
                        stage = f'人员 {person_index}（ID {block.person_ids[person_index-1]}）附件证书 {image.certificate_id} / {image.path}'
                    def after_image(_image):
                        nonlocal completed_images
                        completed_images += 1
                    PersonWordOutputService.insert_images(cursor, images, settings, before_image=before_image, after_image=after_image)
                stage = '分页'
                cursor.page_break()
                completed.append({'block': block.number, 'attachment_position': attachment_position})
            except Exception as error:
                raise AutoFillWriteError(f'Word 输出未完整完成：Block {block.number}，{stage}；已完成 {len(completed)} 个 Block。当前块已完成：{"、".join(completed_stages) or "无"}、{completed_images} 张附件；失败阶段可能已部分写入，其后内容未输出，请检查 Word。原始错误：{error}') from error
        cursor.finish()
        return plan
