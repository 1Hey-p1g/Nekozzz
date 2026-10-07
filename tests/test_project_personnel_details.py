"""Phase 2C read-only details, isolated V1 fixtures; no real Word."""
import unittest
import hashlib
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView
from database.runtime import runtime_connection
from services.projects import ProjectPersonnelEntry
from tests import test_projects as fixtures


class PersonnelDetailsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = f = fixtures.ProjectTests()
        f.setUpClass()
        f.setUp()
        self.addCleanup(f.doCleanups)
        with runtime_connection(f.db, write=True) as connection:
            connection.executemany('INSERT INTO 人员表(人员ID,姓名) VALUES(?,?)', [(4,'王五'),(5,'陈七')])
        f.service.save(f.a, {'项目名称':'A配网'}, personnel=[
            ProjectPersonnelEntry(None,2,'技术负责人'),
            ProjectPersonnelEntry(None,1,'项目负责人'),
            ProjectPersonnelEntry(None,4,'安全员'),
            ProjectPersonnelEntry(None,5,'资料员')])
        f.service.save(f.b, {'项目名称':'B工程'}, personnel=[
            ProjectPersonnelEntry(None,1,'技术负责人'),
            ProjectPersonnelEntry(None,1,'安全负责人'),
            ProjectPersonnelEntry(None,2,'调试负责人')])
        self.c = f.service.save(None, {'项目名称':'C工程'}, personnel=[])
        self.page = f.show_search()

    def select(self, project_id):
        p = self.page
        index = next(i for i,r in enumerate(p.project_model.rows) if r['业绩ID']==project_id)
        p.add_project(p.project_model.index(index,0))
        self.fixture.app.processEvents()
        self.fixture.app.processEvents()

    def texts(self):
        return [(r['role'],r['person_name']) for r in self.page.personnel_model.rows]

    def test_columns_saved_facts_order_and_read_only(self):
        f,p = self.fixture,self.page
        before = hashlib.sha256(f.db.read_bytes()).digest()
        with patch.object(f.service.projects,'project_personnel',wraps=f.service.projects.project_personnel) as query:
            self.select(f.a)
            query.assert_called_once_with(f.a)
        self.assertEqual([('项目负责人','张三'),('技术负责人','李四'),('安全员','王五'),('资料员','陈七')],self.texts())
        self.assertEqual(['担任职务','姓名'],[p.personnel_model.headerData(i,Qt.Horizontal) for i in range(2)])
        self.assertEqual(2,p.personnel_model.columnCount())
        self.assertEqual(QAbstractItemView.NoEditTriggers,p.personnel_view.editTriggers())
        self.assertFalse(p.personnel_model.flags(p.personnel_model.index(0,0)) & Qt.ItemIsEditable)
        self.assertNotIn('项目负责人',[r['字段'] for r in p.info_model.rows])
        self.assertEqual(before,hashlib.sha256(f.db.read_bytes()).digest())
        self.assertLess(p.info_view.geometry().bottom(),p.personnel_view.geometry().top())
        self.assertLess(p.personnel_view.geometry().bottom(),p.types_view.geometry().top())

    def test_switch_multiple_roles_custom_empty_and_no_selection(self):
        f,p = self.fixture,self.page
        self.select(f.a)
        self.select(f.b)
        self.assertEqual([('技术负责人','张三'),('安全负责人','张三'),('调试负责人','李四')],self.texts())
        self.select(self.c)
        self.assertEqual([],self.texts())
        self.assertTrue(p.personnel_view.isVisible())
        self.select(f.a)
        p.task_list.setCurrentRow(-1)
        self.assertEqual(4,len(self.texts()))  # Browsing survives clearing task selection.
        self.select(f.a)
        for project_id in list(p.task_list.person_ids()):
            p.remove_project(project_id)
        self.assertEqual(4,len(self.texts()))  # Removing output items does not remove facts.

    def test_empty_search_preserves_valid_viewed_details(self):
        f,p = self.fixture,self.page
        self.select(f.a)
        p.filters['name'].setText('不存在的工程')
        p.search()
        self.assertEqual(4,len(self.texts()))
        p.clear_search()
        self.assertEqual(4,len(self.texts()))

    def test_copy_single_cell_leaves_task_types_and_search_unchanged(self):
        f,p = self.fixture,self.page
        f.publisher.save_pages((f.a,'合同'),f.pages)
        self.select(f.a)
        p.job.item(f.a).selected_attachment_types.add('合同')
        state = (p.task_list.person_ids(),p.current_id(),set(p.type_model.checked),list(p.project_model.rows),p.projects_view.currentIndex())
        for column,text in ((0,'技术负责人'),(1,'李四')):
            index = p.personnel_model.index(1,column)
            p.personnel_view.scrollTo(index)
            f.app.processEvents()
            point = p.personnel_view.visualRect(index).center()
            QGuiApplication.clipboard().setText('before')
            with patch.object(f.service.projects,'project_personnel',side_effect=AssertionError('copy must not query')):
                QTest.mouseDClick(p.personnel_view.viewport(),Qt.LeftButton,pos=point)
            self.assertEqual(text,QGuiApplication.clipboard().text())
            self.assertEqual(state,(p.task_list.person_ids(),p.current_id(),set(p.type_model.checked),list(p.project_model.rows),p.projects_view.currentIndex()))

    def test_one_three_six_ten_thirty_rows_bounded_geometry(self):
        f,p = self.fixture,self.page
        p.resize(1050,700)
        minimum = None
        for count in (1,3,6,10,30):
            with self.subTest(count=count):
                f.service.save(f.a,{'项目名称':'A配网'},personnel=[ProjectPersonnelEntry(None,1,f'自定义职务{i}') for i in range(count)])
                self.select(self.c)
                self.select(f.a)
                view = p.personnel_view
                self.assertEqual(count,p.personnel_model.rowCount())
                visible = sum(view.rowHeight(i) for i in range(min(count,3)))
                self.assertGreaterEqual(view.viewport().height(),visible)
                self.assertEqual(view.height(),p.table_height_for_rows(view,3))
                if count==10:
                    minimum = p.minimumSizeHint().height()
                if count==30:
                    self.assertEqual(minimum,p.minimumSizeHint().height())
                    self.assertGreater(view.verticalScrollBar().maximum(),0)


if __name__=='__main__':
    unittest.main()
