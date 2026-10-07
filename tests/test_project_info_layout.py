"""Phase 2D actual data viewport regression, production stylesheet and TEMP V1."""
import unittest
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from gui.main_window import STYLE
from services.projects import ProjectPersonnelEntry
from tests import test_project_personnel_details as fixtures


class ProjectInfoLayoutTests(unittest.TestCase):
    def setUp(self):
        self.fixture = t = fixtures.PersonnelDetailsTests()
        t.setUp()
        self.addCleanup(t.doCleanups)
        self.app = t.fixture.app
        original = self.app.styleSheet()
        self.addCleanup(lambda: self.app.setStyleSheet(original))
        self.app.setStyleSheet(STYLE)
        self.page = t.page
        self.page.resize(1050,700)

    def pump(self):
        for _ in range(4):
            self.app.processEvents()

    def people(self, count):
        t,p = self.fixture,self.page
        t.fixture.service.save(t.fixture.a,{'项目名称':'A配网'},personnel=[
            ProjectPersonnelEntry(None,1,f'职务{i}') for i in range(count)])
        t.select(t.c)
        t.select(t.fixture.a)
        self.pump()

    def assert_readable(self):
        p = self.page
        self.assertGreaterEqual(p.info_model.rowCount(),8)
        required = sum(p.info_view.rowHeight(i) for i in range(4))
        self.assertGreaterEqual(p.info_view.viewport().height(),required)
        count = p.personnel_model.rowCount()
        personnel = p.personnel_view
        self.assertGreaterEqual(personnel.viewport().height(),sum(personnel.rowHeight(i) for i in range(min(3,count))))
        maximum = p.table_height_for_rows(personnel,3)
        self.assertEqual(personnel.maximumHeight(),maximum)
        self.assertLessEqual(personnel.height(),maximum)

    def test_normal_window_three_six_ten_thirty_people_actual_viewports(self):
        for count in (3,6,10,30):
            with self.subTest(count=count):
                self.people(count)
                self.assert_readable()
                if count>=10:
                    self.assertGreater(self.page.personnel_view.verticalScrollBar().maximum(),0)

    def test_zero_one_two_people_keep_three_row_blank_space(self):
        self.page.resize(1250,900)
        self.people(6)
        crowded = self.page.info_view.viewport().height()+self.page.preview.height()
        for count in (0,1,2):
            with self.subTest(count=count):
                self.people(count)
                self.assert_readable()
                view = self.page.personnel_view
                required = self.page.table_height_for_rows(view,3)
                self.assertEqual(view.minimumHeight(),required)
                self.assertEqual(view.maximumHeight(),required)
                self.assertGreaterEqual(self.page.info_view.viewport().height()+self.page.preview.height(),crowded)

    def test_expand_restore_and_info_pixel_scrolling(self):
        self.people(10)
        normal = self.page.info_view.viewport().height()
        self.assertGreater(self.page.info_view.verticalScrollBar().maximum(),0)
        self.page.resize(1350,1100)
        self.pump()
        self.assertEqual(self.page.info_view.viewport().height(),normal)
        self.page.resize(1050,700)
        self.pump()
        self.assert_readable()
        bar = self.page.info_view.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.assertEqual(bar.value(),bar.maximum())

    def test_two_tables_double_click_copy_unchanged_after_layout(self):
        self.people(3)
        p = self.page
        for view,model,row,column,expected in (
            (p.info_view,p.info_model,0,1,'A配网'),
            (p.personnel_view,p.personnel_model,0,0,'职务0'),
            (p.personnel_view,p.personnel_model,0,1,'张三')):
            index = model.index(row,column)
            view.scrollTo(index)
            self.pump()
            QGuiApplication.clipboard().setText('before')
            QTest.mouseDClick(view.viewport(),Qt.LeftButton,pos=view.visualRect(index).center())
            self.assertEqual(QGuiApplication.clipboard().text(),expected)


if __name__=='__main__':
    unittest.main()
