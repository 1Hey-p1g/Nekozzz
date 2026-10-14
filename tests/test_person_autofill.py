"""Isolated V1/GUI/fake-Word auto-fill tests; never attach to Microsoft Word."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import hashlib
from copy import deepcopy
from zipfile import ZipFile
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from contextlib import closing
from pathlib import Path
from unittest.mock import patch, MagicMock
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from database.initializer import create_empty_database
from services.people import PeopleService, age_from_identity, gender_from_identity
from services.settings import PdfSettings, SettingsService
from services.person_word import PersonWordPreflightError
from services.autofill.person_task import PersonAutoFillTask
from services.autofill.person_service import PersonAutoFillService, AutoFillPreflightError, AutoFillWriteError, professional_titles, format_project_experience
from services.autofill import template_core as core
from services.autofill.table_xml import fit_table_to_available_width, freeze_inherited_format, flat_package, ending_paragraph
from gui.person_autofill import PersonAutoFillPage
from services.autofill.word_cursor import WordTableCursor
from services.word_service import WordService, WordOperationError
from types import SimpleNamespace


class FakeWord:
    def __init__(self, missing=()):
        self.calls = []
        self.missing = missing
        self.checked_styles = []
        self.resolved_styles = []
    def missing_styles(self, names):
        self.checked_styles.append(names)
        return [n for n in names if n in self.missing]
    def normal_style(self):
        return 'normal'
    def resolve_style(self, name, **options):
        self.resolved_styles.append((name, options['use_normal']))
        return 'normal' if options['use_normal'] else name


class FakeCursor:
    def __init__(self, word):
        self.word, self.position = word, 0
    def available_width(self):
        return 400
    def assert_unchanged(self):
        pass
    def boundary(self):
        pass
    def text(self, text, style, normal):
        self.word.calls.append(('text', text, normal, style))
        self.position += 1
    def table(self, xml):
        self.word.calls.append(('table', xml))
        self.position += 1
    def image_style(self, name, normal):
        self.word.calls.append(('image_style', name, normal))
    def attachment_start(self, position):
        self.position = position
        self.word.attachment_positions = getattr(self.word, 'attachment_positions', []) + [position]
    def insert_inline_image(self, path, **options):
        self.word.calls.append(('image', Path(path).name, options))
        self.position += 1
    def page_break(self):
        self.word.calls.append(('pagebreak',))
        self.position += 1
    def finish(self):
        self.word.calls.append(('finish',))


class DerivedFieldTests(unittest.TestCase):
    def test_project_experience_fullwidth_parentheses_and_empty_roles(self):
        for role in ('项目负责人', '技术负责人', '调试负责人'):
            self.assertEqual(format_project_experience('佛山XX工程', role), f'佛山XX工程（{role}）')
        for role in (None, '', '  ', '\n\t'):
            self.assertEqual(format_project_experience('佛山XX工程', role), '佛山XX工程')
        self.assertEqual(format_project_experience(None, None), '/')
        self.assertEqual(format_project_experience(None, '施工员'), '/（施工员）')

    def test_gender_shape_position_and_unknowns(self):
        for identity, expected in (
                ('110101199001010017', '男'), ('110101199001010026', '女'),
                ('11010119900101001X', '男'), (' 11010119900101002x ', '女'),
                (None, None), ('', None), ('110101900101001', None),
                ('1101011990010100AX', None), ('a1010119900101001X', None),
                ('11010119900101001?', None)):
            with self.subTest(identity=identity):
                self.assertEqual(gender_from_identity(identity), expected)

    def test_titles_ignore_empty_and_nonexact_types_deduplicate_without_ranking(self):
        certificates = [dict(证书类型=kind, 证书名称=name) for kind, name in (
            ('注册证书','职称证'), ('职称证明','不可进入'), (' 职称证','不可进入'),
            ('职称证',None), ('职称证',''), ('职称证','  '),
            ('职称证','高级工程师'), ('职称证',' 工程师 '), ('职称证','高级工程师'))]
        self.assertEqual(professional_titles(certificates), '高级工程师\n工程师')
        self.assertEqual(professional_titles(certificates[:6]), '/')


class CursorPrimitiveTests(unittest.TestCase):
    def test_boundary_adds_paragraph_after_images_but_not_between_empty_groups(self):
        cursor = WordTableCursor.__new__(WordTableCursor)
        cursor.position = 12
        cursor.word = MagicMock()
        cursor.document = MagicMock()
        cursor.document.Range.return_value.Information.return_value = False
        cursor.document.Range.return_value.Paragraphs.Item.return_value.Range.Start = 10
        with patch.object(cursor, 'mutate') as mutate:
            cursor.boundary()
            mutate.assert_called_once_with(cursor.word.insert_paragraph)
            mutate.reset_mock()
            cursor.document.Range.return_value.Paragraphs.Item.return_value.Range.Start = 12
            cursor.boundary()
            mutate.assert_not_called()

    def test_name_paragraph_advances_anchor_before_image_style(self):
        cursor = WordTableCursor.__new__(WordTableCursor)
        cursor.position = 10
        cursor.word = MagicMock()
        cursor.document = MagicMock()
        cursor.document.Range.return_value.Information.return_value = False
        cursor.word.resolve_style.return_value = 'AF person style object'
        def advance(operation):
            operation()
            cursor.position += 1
        with patch.object(cursor, 'mutate', side_effect=advance):
            cursor.text('张三', 'AF person', False)
        self.assertEqual(cursor.position, 12)
        cursor.word.insert_paragraph.assert_called_once()
        cursor.document.Range.assert_called_with(10,11)
        self.assertEqual(cursor.document.Range.return_value.Paragraphs.Item.return_value.Style,
                         'AF person style object')
        cursor.image_style('图片', False)
        cursor.document.Range.assert_called_with(12,12)
        cursor.word.set_selection_style.assert_called_once_with('图片', use_normal=False)

    def test_open_xml_is_collapsed_and_does_not_start_word(self):
        calls = []
        word = WordService(object())
        word.insert_open_xml(SimpleNamespace(Start=4, End=4, InsertXML=calls.append), '<xml/>')
        self.assertEqual(calls, ['<xml/>'])
        with self.assertRaises(WordOperationError):
            word.insert_open_xml(SimpleNamespace(Start=4, End=5), '<xml/>')

    def test_image_anchor_uses_shape_range_end_not_selection_drift(self):
        word = MagicMock()
        document = SimpleNamespace(ProtectionType=-1, TrackRevisions=False, ReadOnly=False,
                                   FullName='owned.docx', Content=SimpleNamespace(End=100))
        selection = SimpleNamespace(StoryType=1, Start=10, End=10,
                                    Range=SimpleNamespace(Duplicate=SimpleNamespace(Start=10)),
                                    Information=lambda _: False)
        ranges = []
        def make_range(start, end):
            ranges.append((start,end))
            return SimpleNamespace(Information=lambda _: False, Select=lambda: None)
        document.Range = make_range
        word.active_document.return_value = document
        word.selection.return_value = selection
        word.insert_inline_image.return_value = SimpleNamespace(Range=SimpleNamespace(End=11))
        cursor = WordTableCursor(word)
        cursor.insert_inline_image(Path('test.jpg'))
        self.assertEqual(cursor.position, 11)
        self.assertEqual(ranges[-1], (11,11))
        self.assertEqual(selection.Start, 10)  # Deliberately does not naturally drift.

    def test_cursor_rejects_table_and_noncollapsed_before_writes(self):
        word = MagicMock()
        for start, end, inside in ((1,2,False), (1,1,True)):
            word.selection.return_value = SimpleNamespace(StoryType=1, Start=start, End=end, Information=lambda _: inside)
            with self.assertRaises(WordOperationError):
                WordTableCursor(word)
        word.insert_open_xml.assert_not_called()
        word.insert_inline_image.assert_not_called()


class AutoFillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='TenderSystem_autofill_')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = self.root/'v1.db'
        create_empty_database(self.db)
        (self.root/'Images').mkdir()
        with closing(sqlite3.connect(self.db)) as c, c:
            for i in range(1, 41):
                c.execute('INSERT INTO 人员表(人员ID,姓名,身份证号,毕业院校,专业) VALUES(?,?,?,?,?)',
                          (i, f'人员{i}', '110101900101001', '学校', '电力'))
                for index, kind in ((1, '注册证书'), (2, '身份证')):
                    cid = i*100+index
                    c.execute('INSERT INTO 人员证书表(证书ID,人员ID,证书类型,证书名称,证书编号) VALUES(?,?,?,?,?)',
                              (cid, i, kind, f'证书{index}', 'Z001' if index == 1 else None))
                    for page in (10, 2, 1):
                        relative = f'Images/{cid}_{page}.jpg'
                        (self.root/relative).write_bytes(b'fake; never passed to real COM')
                        c.execute('INSERT INTO 人员证书图表(证书ID,路径,备注) VALUES(?,?,?)', (cid, relative, str(page)))
            c.executemany('INSERT INTO 公司业绩表(业绩ID,项目名称) VALUES(?,?)', [(1, '甲工程'), (2, '乙工程')])
            c.executemany('INSERT INTO 人员业绩表(人员ID,业绩ID,担任角色) VALUES(?,?,?)', [(1, 1, '技术负责人'), (1, 2, '施工员')])
        self.people = PeopleService(self.db)
        self.word = FakeWord()
        self.service = PersonAutoFillService(self.people, data_root=self.root, word_factory=lambda: self.word, cursor_factory=FakeCursor)
        self.settings = PdfSettings(person_certificate_type_order=('身份证', '注册证书'))
        self.task = PersonAutoFillTask()
        self.template_bytes = self.task.template_path.read_bytes()
        self.db_hash = hashlib.sha256(self.db.read_bytes()).hexdigest()

    def tearDown(self):
        self.assertEqual(self.task.template_path.read_bytes(), self.template_bytes)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), self.db_hash)

    def add(self, count, attachments=False):
        for i in range(1, count+1):
            self.task.add(i, f'人员{i}')
            if attachments:
                self.task.item(i).attachment_certificate_ids = {i*100+1, i*100+2}

    def test_phase1d_template_signature_and_performance_format_preservation(self):
        self.assertEqual(hashlib.sha256(self.template_bytes).hexdigest(),
                         '892ae87bd316d82448cbd297938359417b7a08650f3d40f6c3b182a803119a52')
        _, _, _, template = core.load_template(self.task.template_path)
        self.assertEqual([b.targets()['performance'] for b in core.BLOCKS], [(4,0),(9,0),(14,0)])
        self.assertEqual(len(template.findall('w:tblGrid/w:gridCol', core.NS)), 8)
        self.assertFalse(template.findall('.//w:vMerge', core.NS))
        clone = deepcopy(template)
        for block in core.BLOCKS:
            cell = core.cell_at(clone, block.targets()['performance'])
            original = core.cell_at(template, block.targets()['performance'])
            for text in ('A工程（项目负责人）\nB工程（技术负责人）', '/'):
                filled = deepcopy(cell)
                core.replace_target_text_preserving_format(filled, text)
                self.assertEqual(core.value_text(filled), text)
                for path in ('w:tcPr', 'w:p/w:pPr'):
                    self.assertEqual(core.canonical(filled.find(path, core.NS)),
                                     core.canonical(original.find(path, core.NS)))
            self.assertEqual(cell.find('w:tcPr/w:vAlign', core.NS).get(f'{{{core.W}}}val'), 'center')
        with ZipFile(self.task.template_path) as archive:
            styles = archive.read('word/styles.xml')
        frozen = freeze_inherited_format(clone, styles)
        alignments = [core.cell_at(frozen,b.targets()['performance']).find('w:p/w:pPr/w:jc',core.NS).get(f'{{{core.W}}}val')
                      for b in core.BLOCKS]
        self.assertEqual(alignments, ['left','both','both'])  # Preserve actual template inheritance.
        for block in core.BLOCKS:
            address = block.targets()['performance']
            self.assertEqual(core.canonical(core.cell_at(frozen,address).find('w:tcPr',core.NS)),
                             core.canonical(core.cell_at(template,address).find('w:tcPr',core.NS)))
        package = core.parse_xml(flat_package([frozen, ending_paragraph()]).encode())
        self.assertEqual(len(package), 2)
        self.assertFalse(package.findall('.//w:sectPr', core.NS))

    def test_multiple_project_lines_and_empty_role_mapping_keep_query_order(self):
        self.add(1)
        projects = [dict(ID=i, 业绩ID=i, 项目名称=name, 担任角色=role) for i,name,role in (
            (1,'A工程','项目负责人'), (2,'B工程','技术负责人'), (3,'C工程','安全员'),
            (4,'D工程',None), (5,'E工程','   '))]
        self.task.item(1).table_project_ids = {1,2,3,4,5}
        with patch.object(self.service, 'projects', return_value=projects):
            table = core.parse_xml(self.service.build_plan(self.task,self.settings).blocks[0].table)
        actual = core.value_text(core.cell_at(table,core.BLOCKS[0].targets()['performance']))
        self.assertEqual(actual, 'A工程（项目负责人）\nB工程（技术负责人）\nC工程（安全员）\nD工程\nE工程')

    def test_counts_order_all_nine_fields_unused(self):
        for count in (1, 2, 3, 4, 8, 30, 40):
            self.task.people.clear()
            self.add(count)
            self.task.reorder(list(range(count, 0, -1)))
            plan = self.service.build_plan(self.task, self.settings)
            self.assertEqual(len(plan.blocks), (count+2)//3)
            names = []
            for b in plan.blocks:
                table = core.parse_xml(b.table)
                self.assertEqual(len(table.findall('w:tr', core.NS)), 15)
                for slot in core.BLOCKS:
                    values = {field: core.value_text(core.cell_at(table, addr)) for field, addr in slot.targets().items()}
                    if slot.slot >= len(b.person_ids):
                        self.assertEqual(set(values.values()), {'/'})
                    else:
                        names.append(values['name'])
                        self.assertEqual(values['age'], str(age_from_identity('110101900101001')))
                        self.assertEqual(values['gender'], '/')
                        self.assertEqual(values['school'], '学校')
                        self.assertEqual(values['major'], '电力')
                        for field in ('title', 'registration', 'role', 'performance'):
                            self.assertEqual(values[field], '/')
            self.assertEqual(names, [f'人员{i}' for i in range(count, 0, -1)])

    def test_registration_projects_role_independent_selection(self):
        self.add(1)
        entry = self.task.item(1)
        entry.role_text = '本次项目负责人'
        entry.table_certificate_ids = {101, 102}
        entry.table_project_ids = {1, 2}
        plan = self.service.build_plan(self.task, self.settings)
        table = core.parse_xml(plan.blocks[0].table)
        fields = {k: core.value_text(core.cell_at(table, v)) for k,v in core.BLOCKS[0].targets().items()}
        self.assertEqual(fields['registration'], '证书1 Z001\n证书2')
        self.assertEqual(fields['performance'], '乙工程（施工员）\n甲工程（技术负责人）')
        self.assertEqual(fields['role'], '本次项目负责人')
        self.assertEqual(plan.image_count, 0)
        entry.attachment_certificate_ids.add(102)
        self.assertEqual(self.service.build_plan(self.task, self.settings).image_count, 3)
        self.assertEqual(entry.table_certificate_ids, {101, 102})

    def test_shared_attachment_sort_and_all_block_call_order(self):
        self.add(4, True)
        self.task.title_text, self.task.note_text = 'T', 'N\n多行'
        for title, note in ((False, False), (True, False), (False, True), (True, True)):
            self.task.include_title, self.task.include_note = title, note
            self.word.calls.clear()
            self.word.attachment_positions = []
            plan = self.service.insert(self.task, self.settings)
            kinds = [call[0] for call in self.word.calls]
            expected = []
            for b in plan.blocks:
                if title: expected.append('text')
                expected.append('table')
                if note: expected.append('text')
                for images in b.images_by_person:
                    expected.append('text')  # Independent person group header.
                    expected.append('image_style')
                    expected.extend(['image'] * len(images))
                expected.append('pagebreak')
            self.assertEqual(kinds, expected+['finish'])
            self.assertEqual(len(self.word.attachment_positions), 2)
            images = [v[1] for v in self.word.calls if v[0] == 'image']
            self.assertEqual(images[:6], ['102_1.jpg','102_2.jpg','102_10.jpg','101_1.jpg','101_2.jpg','101_10.jpg'])
            self.assertEqual(len(self.task.people), 4)

    def test_width_only_shrink_ratios_and_merged_cell_widths(self):
        original = core.load_template(self.task.template_path)[3]
        widths = [int(c.get(f'{{{core.W}}}w')) for c in original.findall('w:tblGrid/w:gridCol', core.NS)]
        for available in (600, 510.8, 460, 400):
            table = fit_table_to_available_width(original, available)
            new = [int(c.get(f'{{{core.W}}}w')) for c in table.findall('w:tblGrid/w:gridCol', core.NS)]
            self.assertAlmostEqual(sum(new)/20, min(available, sum(widths)/20), delta=.05)
            for a,b in zip(widths,new):
                self.assertAlmostEqual(b, a*sum(new)/sum(widths), delta=1)
            for row in table.findall('w:tr', core.NS):
                self.assertEqual(sum(int(c.find('w:tcPr/w:tcW',core.NS).get(f'{{{core.W}}}w')) for c in row.findall('w:tc', core.NS)), sum(new))
            if available >= 510.8:
                self.assertEqual(core.canonical(table), core.canonical(original))

    def test_invalid_ownership_zero_mutations(self):
        self.add(2)
        for attribute, ids in (('table_certificate_ids', {201}), ('attachment_certificate_ids', {201}), ('table_project_ids', {999})):
            setattr(self.task.item(1), attribute, ids)
            with self.assertRaises(AutoFillPreflightError):
                self.service.insert(self.task, self.settings)
            setattr(self.task.item(1), attribute, set())
        self.assertEqual(self.word.calls, [])

    def test_missing_attachment_preflight_zero_mutations(self):
        self.add(1, True)
        (self.root/'Images/101_10.jpg').unlink()
        with self.assertRaises(PersonWordPreflightError):
            self.service.insert(self.task, self.settings)
        self.assertEqual(self.word.calls, [])

    def test_modified_template_rejected_before_word(self):
        self.add(1)
        path = self.root/'modified.docx'
        path.write_bytes(self.template_bytes+b'changed')
        self.task.template_path = path
        with self.assertRaises(ValueError):
            self.service.insert(self.task, self.settings)
        self.assertEqual(self.word.calls, [])
        self.task.template_path = PersonAutoFillTask().template_path

    def test_fallback_cancel_zero_writes_and_normal_for_missing_only(self):
        self.add(1, True)
        self.task.include_title, self.task.title_text = True, 'T'
        self.settings = replace(self.settings, autofill_title_style='AF title',
                                autofill_note_style='AF note', autofill_person_name_style='AF name')
        self.word.missing = [self.settings.image_style, self.settings.autofill_title_style,
                             self.settings.autofill_person_name_style]
        confirmations = []
        with self.assertRaises(AutoFillPreflightError):
            self.service.insert(self.task, self.settings, confirm_style_fallback=lambda missing: False)
        self.assertEqual(self.word.calls, [])
        self.service.insert(self.task, self.settings, confirm_style_fallback=lambda missing: confirmations.append(missing) or True)
        self.assertEqual(len(confirmations), 1)
        self.assertTrue(next(c for c in self.word.calls if c[0]=='text')[2])
        self.assertTrue(next(c for c in self.word.calls if c[0]=='image_style')[2])
        self.assertEqual(confirmations[0], [('自动填表表头', 'AF title'),
                                           ('自动填表人员姓名', 'AF name'),
                                           ('图片样式', self.settings.image_style)])

    def test_gender_and_titles_from_all_certificates_not_task_selections(self):
        self.add(1)
        for names in ((), ('工程师',), ('高级工程师',), ('高级工程师', '工程师', '工程师')):
            with self.subTest(names=names):
                extra = [{'证书ID': 900+i, '证书类型': '职称证', '证书名称': name,
                          '证书编号': 'not a title'} for i, name in enumerate(names)]
                existing = self.service.certificates(1)
                person = self.people.people.get(1)
                person['身份证号'] = '11010119900101001X'
                with patch.object(self.service, 'certificates', return_value=existing+extra), \
                     patch.object(self.people.people, 'get', return_value=person):
                    plan = self.service.build_plan(self.task, self.settings)
                table = core.parse_xml(plan.blocks[0].table)
                fields = {k: core.value_text(core.cell_at(table, v)) for k,v in core.BLOCKS[0].targets().items()}
                self.assertEqual(fields['gender'], '男')
                self.assertEqual(fields['title'], '\n'.join(dict.fromkeys(names)) or '/')
                self.assertEqual(fields['registration'], '/')
                self.assertEqual(plan.image_count, 0)
                self.assertEqual(self.task.item(1).table_certificate_ids, set())
                self.assertEqual(self.task.item(1).attachment_certificate_ids, set())

    def test_title_derivation_preserves_real_repository_order(self):
        self.add(1)
        with closing(sqlite3.connect(self.db)) as c, c:
            c.executemany('INSERT INTO 人员证书表(证书ID,人员ID,证书类型,证书名称) VALUES(?,1,?,?)',
                          [(5000, '职称证', '高级工程师'), (5001, '职称证', '工程师'),
                           (5002, '职称证', '工程师'), (5003, '职称证明', '不得进入')])
        self.db_hash = hashlib.sha256(self.db.read_bytes()).hexdigest()
        expected = professional_titles(self.people.certificates.for_person(1, document_order=True))
        table = core.parse_xml(self.service.build_plan(self.task, self.settings).blocks[0].table)
        actual = core.value_text(core.cell_at(table, core.BLOCKS[0].targets()['title']))
        self.assertEqual(actual, expected)
        self.assertEqual(actual, '工程师\n高级工程师')

    def test_only_used_independent_styles_preflight_and_default_normal(self):
        self.add(1)
        settings = replace(self.settings, person_name_style='ordinary missing',
                           image_style='image missing', autofill_title_style='title missing',
                           autofill_note_style='note missing', autofill_person_name_style='AF name')
        self.word.missing = ['ordinary missing', 'image missing', 'title missing', 'note missing']
        self.service.insert(self.task, settings)
        self.assertEqual(self.word.checked_styles[-1], ['AF name'])
        self.assertEqual(self.word.calls[1], ('text', '人员1', False, 'AF name'))
        self.word.calls.clear()
        self.service.insert(self.task, self.settings)
        self.assertEqual(self.word.checked_styles[-1], [])
        self.assertEqual(self.word.resolved_styles[-1], ('', True))
        self.assertEqual(self.word.calls[1], ('text', '人员1', True, ''))

    def test_independent_title_note_name_styles_and_empty_person_groups(self):
        self.add(3)
        self.task.include_title = self.task.include_note = True
        self.task.title_text, self.task.note_text = 'T', 'N'
        self.task.item(2).attachment_certificate_ids = {201}
        settings = replace(self.settings, person_name_style='ordinary unused',
                           autofill_title_style='T style', autofill_note_style='N style',
                           autofill_person_name_style='P style')
        self.service.insert(self.task, settings)
        events = [(c[0], c[1] if c[0] != 'table' and len(c)>1 else '') for c in self.word.calls]
        self.assertEqual(events, [('text','T'), ('table',''), ('text','N'),
                                 ('text','人员1'), ('text','人员2'), ('image_style',settings.image_style),
                                 ('image','201_1.jpg'), ('image','201_2.jpg'), ('image','201_10.jpg'),
                                 ('text','人员3'), ('pagebreak',''), ('finish','')])
        self.assertEqual([c[3] for c in self.word.calls if c[0]=='text'],
                         ['T style','N style','P style','P style','P style'])
        self.assertEqual(self.word.checked_styles[-1], ['T style','N style','P style',settings.image_style])
        self.assertEqual(self.word.attachment_positions, [3])  # After note, before first name.

    def test_missing_autofill_styles_once_cancel_or_selective_normal_without_settings_write(self):
        self.add(1)
        self.task.include_title = self.task.include_note = True
        self.task.title_text, self.task.note_text = 'T', 'N'
        service = SettingsService(self.root/'settings.json')
        settings = replace(self.settings, autofill_title_style='title',
                           autofill_note_style='note', autofill_person_name_style='name')
        service.save(settings)
        before = service.path.read_bytes()
        for missing in (('title',), ('note',), ('name',), ('title','note','name')):
            with self.subTest(missing=missing):
                self.word.calls.clear()
                self.word.missing = missing
                confirmations = []
                with self.assertRaises(AutoFillPreflightError):
                    self.service.insert(self.task, service.load(),
                                        confirm_style_fallback=lambda items: confirmations.append(items) or False)
                self.assertEqual(self.word.calls, [])
                self.assertEqual(len(confirmations), 1)
                confirmations.clear()
                self.service.insert(self.task, service.load(),
                                    confirm_style_fallback=lambda items: confirmations.append(items) or True)
                self.assertEqual(len(confirmations), 1)
                texts = [c for c in self.word.calls if c[0]=='text']
                self.assertEqual([c[2] for c in texts], [s in missing for s in ('title','note','name')])
                self.assertEqual(service.path.read_bytes(), before)

    def test_eight_people_no_unused_person_group(self):
        self.add(8)
        self.service.insert(self.task, self.settings)
        names = [c[1] for c in self.word.calls if c[0]=='text']
        self.assertEqual(names, [f'人员{i}' for i in range(1,9)])
        self.assertEqual(sum(c[0]=='pagebreak' for c in self.word.calls), 3)
        last_table = max(i for i,c in enumerate(self.word.calls) if c[0]=='table')
        self.assertEqual([c[1] for c in self.word.calls[last_table:] if c[0]=='text'], ['人员7','人员8'])

    def test_mid_write_failure_reports_block_stage(self):
        self.add(4)
        with patch.object(FakeCursor, 'table', side_effect=RuntimeError('test COM failure')):
            with self.assertRaisesRegex(AutoFillWriteError, 'Block 1，表格'):
                self.service.insert(self.task, self.settings)

    def test_gui_session_selection_and_role_are_independent(self):
        page = PersonAutoFillPage(self.people, self.service, SettingsService(self.root/'settings.json'), lambda *_: None)
        self.addCleanup(page.close)
        page.add_person(page.people_model.index(0,0))
        page.add_person(page.people_model.index(1,0))
        self.assertEqual(len(page.task.people), 2)
        current = page.task.item(page.current_id())
        page.role_changed('技术负责人')
        self.assertEqual(current.role_text, '技术负责人')
        page.table_certificates.setData(page.table_certificates.index(0,0), Qt.Checked, Qt.CheckStateRole)
        self.assertEqual(len(current.table_certificate_ids), 1)
        self.assertEqual(current.attachment_certificate_ids, set())
        self.assertEqual(current.table_project_ids, set())
        ids = [p.person_id for p in page.task.people]
        page.task.reorder(ids[::-1])
        page.refresh(current.person_id)
        self.assertEqual(page.task_list.person_ids(), ids[::-1])
        page.remove_person(ids[0])
        self.assertIs(page.task.item(current.person_id), current)
        item = page.task_list.item(0)
        self.assertGreaterEqual(item.sizeHint().height(), page.task_list.itemWidget(item).sizeHint().height())


if __name__ == '__main__':
    unittest.main()
