"""Phase 2F browser/task separation and stable style-derived row budgets."""
import unittest
import hashlib
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from gui.main_window import STYLE
from services.projects import ProjectPersonnelEntry
from tests import test_projects as projects
from tests import test_person_word as people


def click_result(view, model, key, value, *, double=False):
    row = next(i for i,r in enumerate(model.rows) if r[key]==value)
    index = model.index(row,0)
    view.scrollTo(index)
    point = view.visualRect(index).center()
    if double:
        QTest.mouseClick(view.viewport(),Qt.LeftButton,pos=point)
        QTest.mouseDClick(view.viewport(),Qt.LeftButton,pos=point)
    else:
        QTest.mouseClick(view.viewport(),Qt.LeftButton,pos=point)


def click_task(view, row):
    QTest.mouseClick(view.viewport(),Qt.LeftButton,pos=view.visualItemRect(view.item(row)).center())


class ProjectBrowserTests(unittest.TestCase):
    def setUp(self):
        self.f = f = projects.ProjectTests()
        f.setUpClass()
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.ids = [f.a,f.b]
        for name in ('C工程','D工程'):
            self.ids.append(f.service.save(None,{'项目名称':name},personnel=[]))
        for project_id,count in zip(self.ids,(0,1,3,10)):
            f.service.save(project_id,{'项目名称':f.service.projects.get(project_id)['项目名称']},
                personnel=[ProjectPersonnelEntry(None,1,f'职务{i}') for i in range(count)])
            for i in range(min(count,5)):
                f.publisher.save_pages((project_id,f'类型{i}'),f.pages)
        self.page = f.show_search()
        original = f.app.styleSheet()
        self.addCleanup(lambda:f.app.setStyleSheet(original))
        f.app.setStyleSheet(STYLE)
        self.page.resize(1050,700)
        self.pump()

    def pump(self):
        for _ in range(4):
            self.f.app.processEvents()

    def browse(self, project_id, double=False):
        click_result(self.page.projects_view,self.page.project_model,'业绩ID',project_id,double=double)
        self.pump()

    def test_four_three_three_stable_across_empty_one_three_ten_and_resize(self):
        p = self.page
        baseline = None
        positions = None
        for project_id in self.ids:
            self.browse(project_id)
            views = (p.info_view,p.personnel_view,p.types_view)
            heights = tuple(v.height() for v in views)
            self.assertEqual(heights,tuple(p.table_height_for_rows(v,n) for v,n in zip(views,(4,3,3))))
            self.assertTrue(all(v.minimumHeight()==v.maximumHeight() for v in views))
            if baseline is None:
                baseline = heights
                positions = tuple(v.y() for v in views)
            self.assertEqual(baseline,heights)
            self.assertEqual(positions,tuple(v.y() for v in views))
        self.assertGreater(p.personnel_view.verticalScrollBar().maximum(),0)
        self.assertGreater(p.types_view.verticalScrollBar().maximum(),0)
        for width,height in ((1350,1500),(1000,600),(1050,700)):
            p.resize(width,height)
            self.pump()
            self.assertEqual(baseline,tuple(v.height() for v in views))
        self.assertGreaterEqual(p.preview.height(),p.preview.minimumHeight())

    def test_single_view_double_add_idempotent_without_db_or_word_writes(self):
        p,f = self.page,self.f
        before = hashlib.sha256(f.db.read_bytes()).digest()
        with patch.object(p.output_service,'insert',side_effect=AssertionError('browsing must not write Word')):
            self.browse(f.a)
            self.assertEqual(f.a,p.viewed_project_id)
            self.assertEqual([],p.job.projects)
            self.browse(f.a,True)
            self.browse(f.a,True)
            self.assertEqual([f.a],p.task_list.person_ids())
            self.browse(f.b)
            self.assertEqual(f.b,p.viewed_project_id)
            self.assertEqual([f.a],p.task_list.person_ids())
            self.assertEqual(f.a,p.task_current_id())
        self.assertEqual(before,hashlib.sha256(f.db.read_bytes()).digest())

    def test_task_click_remove_and_empty_search_preserve_valid_browsing(self):
        p,f = self.page,self.f
        self.browse(f.a,True)
        self.browse(f.b)
        click_task(p.task_list,0)  # Already-current task still navigates from browser B.
        self.assertEqual(f.a,p.viewed_project_id)
        p.remove_project(f.a)
        self.assertEqual([],p.job.projects)
        self.assertEqual(f.a,p.viewed_project_id)
        self.assertTrue(p.info_model.rows)
        p.filters['name'].setText('not found')
        p.search()
        self.assertEqual(f.a,p.viewed_project_id)
        f.service.delete(f.a)
        p.search()
        self.assertIsNone(p.viewed_project_id)
        self.assertEqual([],p.info_model.rows)

    def test_unowned_attachments_browse_only_then_existing_task_set_used(self):
        p,f = self.page,self.f
        self.browse(f.b)
        self.assertTrue(p.attachment_model.rows)
        self.assertIsNotNone(p.preview._pixmap)
        index = p.type_model.index(0,0)
        self.assertFalse(index.flags() & Qt.ItemIsEnabled)
        self.assertFalse(p.type_model.setData(index,Qt.Checked,Qt.CheckStateRole))
        QTest.mouseClick(p.types_view.viewport(),Qt.LeftButton,pos=p.types_view.visualRect(index).center())
        self.assertEqual([],p.job.projects)
        self.browse(f.b,True)
        self.assertIs(p.type_model.checked,p.job.item(f.b).selected_attachment_types)
        index = p.type_model.index(0,0)
        self.assertTrue(index.flags() & Qt.ItemIsUserCheckable)
        QTest.mouseClick(p.types_view.viewport(),Qt.LeftButton,pos=p.types_view.visualRect(index).center())
        self.assertEqual({'类型0'},p.job.item(f.b).selected_attachment_types)
        p.remove_project(f.b)
        self.assertEqual(f.b,p.viewed_project_id)
        self.assertFalse(p.type_model.checks_enabled)
        self.assertTrue(p.attachment_model.rows)


class PersonBrowserTests(unittest.TestCase):
    def setUp(self):
        self.f = f = people.PersonWordTests()
        f.setUpClass()
        f.setUp()
        self.addCleanup(f.doCleanups)
        _,self.page = f._show_multi_page()

    def browse(self, person_id, double=False):
        click_result(self.page.people_view,self.page.people_model,'人员ID',person_id,double=double)
        self.f.app.processEvents()

    def test_single_view_double_add_duplicate_and_task_navigation(self):
        p = self.page
        before = hashlib.sha256(self.f.db.read_bytes()).digest()
        self.browse(1)
        self.assertEqual(1,p.viewed_person_id)
        self.assertIn('张三',p.person_info.text())
        self.assertEqual([],p.job.persons)
        self.browse(1,True)
        self.browse(1,True)
        self.assertEqual([1],p.task_list.person_ids())
        self.browse(2)
        self.assertEqual(2,p.viewed_person_id)
        self.assertEqual([1],p.task_list.person_ids())
        self.browse(2,True)
        self.assertEqual([1,2],p.task_list.person_ids())
        click_task(p.task_list,0)
        self.assertEqual(1,p.viewed_person_id)
        p.remove_person(1)
        self.assertEqual([2],p.task_list.person_ids())
        self.assertEqual(1,p.viewed_person_id)
        self.assertIn('张三',p.person_info.text())
        self.assertEqual(before,hashlib.sha256(self.f.db.read_bytes()).digest())
        self.assertEqual([],self.f.word.calls)

    def test_certificate_selection_disabled_until_added_and_owned_set_independent(self):
        p = self.page
        self.browse(1)
        self.assertTrue(p.certificate_model.rows)
        self.assertTrue(p.attachment_model.rows)
        self.assertIsNotNone(p.preview._pixmap)
        index = p.certificate_model.index(0,0)
        self.assertFalse(index.flags() & Qt.ItemIsUserCheckable)
        self.assertFalse(p.certificate_model.setData(index,Qt.Checked,Qt.CheckStateRole))
        QTest.mouseClick(p.certificates_view.viewport(),Qt.LeftButton,pos=p.certificates_view.visualRect(index).center())
        self.assertEqual([],p.job.persons)
        self.browse(1,True)
        self.assertIs(p.certificate_model.checked,p.job.item(1).selected_certificate_ids)
        index = p.certificate_model.index(0,0)
        QTest.mouseClick(p.certificates_view.viewport(),Qt.LeftButton,pos=p.certificates_view.visualRect(index).center())
        expected = {p.certificate_model.rows[0]['证书ID']}
        self.assertEqual(expected,p.job.item(1).selected_certificate_ids)
        self.browse(2)
        self.assertFalse(p.certificate_model.checks_enabled)
        self.assertEqual(expected,p.job.item(1).selected_certificate_ids)
        self.browse(1)
        self.assertEqual(expected,p.certificate_model.checked)
        p.remove_person(1)
        self.assertEqual(1,p.viewed_person_id)
        self.assertFalse(p.certificate_model.checks_enabled)

    def test_search_refresh_clears_filtered_view_and_invalid_person(self):
        p = self.page
        self.browse(2)
        p.name_filter.setText('not found')
        p.search_people()
        self.assertIsNone(p.viewed_person_id)
        self.assertEqual([],p.certificate_model.rows)
        p.name_filter.clear()
        p.search_people()
        self.browse(2)
        with patch.object(self.f.people.people,'get',return_value=None):
            p.search_people()
        self.assertIsNone(p.viewed_person_id)
        self.assertEqual([],p.certificate_model.rows)


if __name__=='__main__':
    unittest.main()
