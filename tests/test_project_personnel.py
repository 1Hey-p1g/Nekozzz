"""Phase 2A isolated relation CRUD, draft GUI and AutoFill integration."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import sqlite3
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from database.initializer import create_empty_database
from database.runtime import runtime_connection
from services.projects import ProjectService, ProjectPersonnelEntry as Entry
from services.people import PeopleService
from services.settings import SettingsService, PdfSettings
from services.attachments import ProjectAttachmentService
from services.autofill.person_task import PersonAutoFillTask
from services.autofill.person_service import PersonAutoFillService, AutoFillPreflightError
from services.autofill import template_core as core
from gui.project_manage import ProjectManagePage
from gui.project_personnel import COMMON_PROJECT_ROLES
from gui.person_autofill import PersonAutoFillPage


class ProjectPersonnelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='TenderSystem_project_personnel_')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = self.root/'v1.db'
        create_empty_database(self.db)
        with runtime_connection(self.db, write=True) as c:
            c.executemany('INSERT INTO 人员表(人员ID,姓名) VALUES(?,?)',
                          [(1,'张三'),(2,'李四'),(3,'王五'),(4,'赵六'),(5,'张三')])
        self.service = ProjectService(self.db)
        self.a = self.save(None, [Entry(person_id=i, role=role) for i,role in (
            (1,'项目负责人'),(2,'技术负责人'),(3,'安全员'),(4,'资料员'))], '佛山A工程')
        self.b = self.save(None, [Entry(person_id=1,role='技术负责人'), Entry(person_id=1,role='安全负责人')], '佛山B工程')
        self.c = self.save(None, [], '空工程')
        self.people = PeopleService(self.db)
        self.settings = SettingsService(self.root/'settings.json')

    def entries(self, project_id):
        return [Entry(r['relation_id'], r['person_id'], r['role'])
                for r in self.service.projects.project_personnel(project_id)]

    def save(self, project_id, entries, name='工程'):
        return self.service.save(project_id, {'项目名称':name}, personnel=entries)

    def snapshot(self):
        with runtime_connection(self.db) as c:
            return (list(map(tuple,c.execute('SELECT * FROM 公司业绩表 ORDER BY 业绩ID'))),
                    list(map(tuple,c.execute('SELECT * FROM 人员业绩表 ORDER BY ID'))))

    def page(self):
        page = ProjectManagePage(self.service, settings_service=self.settings,
                                 attachment_service=ProjectAttachmentService(self.db,data_root=self.root),
                                 notify=lambda *_:None)
        self.addCleanup(page.close)
        return page

    def test_schema_and_foreign_key_safety_unchanged(self):
        with runtime_connection(self.db) as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],1)
            sql = c.execute("SELECT sql FROM sqlite_master WHERE name='人员业绩表'").fetchone()[0]
            self.assertIn('UNIQUE ("人员ID", "业绩ID", "担任角色")', sql)
            indexes = {r['name']:r for r in c.execute('PRAGMA index_list(人员业绩表)')}
            self.assertEqual(indexes['ux_人员业绩_单项目负责人']['partial'],1)
            self.assertEqual(indexes['ux_人员业绩_单项目负责人']['unique'],1)
            self.assertEqual([(r['on_update'],r['on_delete']) for r in c.execute('PRAGMA foreign_key_list(人员业绩表)')],
                             [('RESTRICT','RESTRICT')]*2)
        for table, key, row_id in (('人员表','人员ID',1),('公司业绩表','业绩ID',self.a)):
            with self.assertRaises(sqlite3.IntegrityError), runtime_connection(self.db, write=True) as c:
                c.execute(f'DELETE FROM {table} WHERE {key}=?',(row_id,))
        with self.assertRaisesRegex(ValueError,'人员任职'):
            self.service.delete(self.a)
        with self.assertRaisesRegex(ValueError,'关联'):
            self.people.delete_person(1)

    def test_many_people_same_person_multiple_roles_custom_and_zero(self):
        self.assertEqual(len(self.entries(self.a)),4)
        self.assertEqual([(r.person_id,r.role) for r in self.entries(self.b)],[(1,'技术负责人'),(1,'安全负责人')])
        entries = self.entries(self.a)+[Entry(person_id=2,role='  调试负责人  ')]
        self.save(self.a,entries)
        self.assertEqual(self.entries(self.a)[-1].role,'调试负责人')
        self.assertEqual(self.entries(self.c),[])
        self.save(self.c,[])

    def test_edit_remove_and_preserve_relation_ids(self):
        entries = self.entries(self.a)
        ids = [e.relation_id for e in entries]
        entries[0].person_id = 5
        entries[1].role = '现场负责人'
        self.save(self.a,entries[:-1])
        saved = self.entries(self.a)
        self.assertEqual([e.relation_id for e in saved],ids[:-1])
        self.assertEqual(saved[0].person_id,5)
        self.assertEqual(saved[1].role,'现场负责人')
        self.save(self.a,[])
        self.assertEqual(self.entries(self.a),[])

    def test_leader_becomes_other_role_and_role_swaps_are_atomic(self):
        entries = self.entries(self.a)
        entries[0].role, entries[1].role = entries[1].role,entries[0].role
        self.save(self.a,entries)
        self.assertEqual(self.service.projects.get(self.a)['负责人ID'],2)
        entries[1].role = '技术负责人'
        self.save(self.a,entries)
        self.assertIsNone(self.service.projects.get(self.a)['负责人ID'])

    def test_all_invalid_rows_reject_before_save(self):
        before = self.snapshot()
        bad = ([Entry(person_id=1,role='')], [Entry(person_id=1,role=' \t ')],
               [Entry(person_id=None,role='技术负责人')], [Entry(person_id=999,role='技术负责人')],
               [Entry(person_id=1,role='技术负责人'),Entry(person_id=1,role=' 技术负责人 ')],
               [Entry(person_id=1,role='项目负责人'),Entry(person_id=2,role=' 项目负责人 ')])
        for entries in bad:
            with self.subTest(entries=entries), self.assertRaisesRegex(ValueError,'第 .* 行'):
                self.save(self.a,entries,'不可保存')
            self.assertEqual(self.snapshot(),before)
        self.save(self.c,[Entry(person_id=1,role='现场负责人'),Entry(person_id=2,role='项目副经理')])

    def test_transaction_rolls_back_project_and_all_relations(self):
        before = self.snapshot()
        with patch.object(self.service.projects,'_sync_personnel',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):
                self.save(None,[Entry(person_id=1,role='质量员')],'不可新增')
            with self.assertRaises(RuntimeError):
                self.save(self.a,[],'不可修改')
        self.assertEqual(self.snapshot(),before)
        # Trigger fails on the second relation, after the first has been inserted.
        with runtime_connection(self.db,write=True) as c:
            c.execute("CREATE TRIGGER test_failure BEFORE INSERT ON 人员业绩表 WHEN NEW.担任角色='测试失败' "
                      "BEGIN SELECT RAISE(ABORT,'injected'); END")
        for project_id in (None,self.a):
            with self.assertRaises(sqlite3.IntegrityError):
                self.save(project_id,[Entry(person_id=1,role='质量员'),Entry(person_id=2,role='测试失败')],'不可保存')
            self.assertEqual(self.snapshot(),before)

    def test_relation_ownership_failure_rolls_back_basic_fields(self):
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError,'关系不属于'):
            self.save(self.a,self.entries(self.b),'不可保存')
        self.assertEqual(self.snapshot(),before)

    def test_leader_search_does_not_match_other_roles(self):
        self.assertEqual([r['业绩ID'] for r in self.service.search(leader='张三')],[self.a])
        self.save(self.a,[replace(e,role='技术负责人') if e.role=='项目负责人' else e for e in self.entries(self.a)])
        self.assertEqual(self.service.search(leader='张三'),[])

    def test_gui_all_rows_custom_role_same_name_id_and_save_reload(self):
        page = self.page()
        page.project_id = self.a
        page.load(self.service.projects.get(self.a))
        self.assertEqual(len(page.personnel.rows),4)
        self.assertFalse(hasattr(page,'leader'))
        page.set_mode('edit')
        entry, _, role, person, _ = page.personnel.rows[0]
        self.assertTrue(role.isEditable())
        self.assertEqual([role.itemText(i) for i in range(role.count())],list(COMMON_PROJECT_ROLES))
        self.assertFalse(person.isEditable())
        self.assertNotEqual(person.itemText(person.findData(1)),person.itemText(person.findData(5)))
        person.setCurrentIndex(person.findData(5))
        role.setCurrentText('调试负责人')
        self.assertEqual((entry.person_id,entry.role),(5,'调试负责人'))
        page.save_project()
        self.assertEqual(page.mode,'view')
        self.assertIn((5,'调试负责人'),[(e.person_id,e.role) for e in self.entries(self.a)])
        page.load(self.service.projects.get(self.a))
        self.assertEqual(len(page.personnel.rows),4)

    def test_gui_add_delete_new_cancel_and_invalid(self):
        page = self.page()
        before = self.snapshot()
        page.new_project()
        page.inputs['项目名称'].setText('新项目管理人员')
        entry = page.personnel.add_entry()
        page.save_project()
        self.assertIn('第 1 行',page.error_label.text())
        self.assertEqual(self.snapshot(),before)
        _,_,role,person,_ = page.personnel.rows[0]
        role.setCurrentText('质量员')
        person.setCurrentIndex(person.findData(2))
        page.save_project()
        created = page.project_id
        self.assertEqual([(e.person_id,e.role) for e in self.entries(created)],[(2,'质量员')])
        before = self.snapshot()
        page.set_mode('edit')
        page.personnel.rows[0][-1].click()
        page.personnel.add_entry()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Discard):
            page.cancel()
        self.assertEqual(self.snapshot(),before)
        self.assertEqual([(e.person_id,e.role) for e in page.personnel.entries],[(2,'质量员')])

    def test_gui_scroll_height_does_not_grow_with_rows(self):
        page = self.page()
        page.resize(1050,700)
        page.show()
        page.set_mode('edit')
        self.app.processEvents()
        before = page.size()
        minimum = page.minimumSizeHint().height()
        with patch.object(self.service.people,'search',side_effect=AssertionError('No per-row database query')):
            for _ in range(30):
                page.personnel.add_entry()
        self.app.processEvents()
        self.assertEqual(page.size(),before)
        self.assertEqual(page.minimumSizeHint().height(),minimum)
        self.assertGreater(page.personnel.scroll.verticalScrollBar().maximum(),0)

    def test_autofill_selects_relations_independently_and_checks_ownership(self):
        service = PersonAutoFillService(self.people,data_root=self.root)
        page = PersonAutoFillPage(self.people,service,self.settings,lambda *_:None)
        self.addCleanup(page.close)
        page.task.add(1,'张三')
        page.refresh(1)
        records = self.people.people.projects(1)
        b = [r for r in records if r['业绩ID']==self.b]
        self.assertEqual([r['担任角色'] for r in b],['技术负责人','安全负责人'])
        self.assertNotEqual(b[0]['ID'],b[1]['ID'])
        entry = page.task.item(1)
        for selected, expected in (({b[0]['ID']},'佛山B工程（技术负责人）'),
                                   ({b[1]['ID']},'佛山B工程（安全负责人）'),
                                   ({r['ID'] for r in b},'佛山B工程（技术负责人）\n佛山B工程（安全负责人）')):
            entry.table_project_ids.clear()
            page.show_person()
            for index, record in enumerate(page.project_model.rows):
                if record['ID'] in selected:
                    page.project_model.setData(page.project_model.index(index,0),Qt.Checked,Qt.CheckStateRole)
            self.assertEqual(entry.table_project_ids,selected)
            table = core.parse_xml(service.build_plan(page.task,PdfSettings()).blocks[0].table)
            self.assertEqual(core.value_text(core.cell_at(table,core.BLOCKS[0].targets()['performance'])),expected)
        foreign = self.people.people.projects(2)[0]['ID']
        entry.table_project_ids = {foreign}
        with self.assertRaises(AutoFillPreflightError):
            service.build_plan(page.task,PdfSettings())


if __name__ == '__main__':
    unittest.main()
