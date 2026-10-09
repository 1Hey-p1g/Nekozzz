"""Company information GUI/data tests use only isolated V1 test databases."""
import unittest
from unittest.mock import patch
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from database.runtime import runtime_connection
from gui.theme import ThemeManager
from repositories.qualification_repository import COMPANY_FIELDS
from tests import test_qualifications as qualification_fixture


class CompanyInfoTests(unittest.TestCase):
    setUp = qualification_fixture.QualificationTests.setUp
    search_page = qualification_fixture.QualificationTests.search_page
    manage_page = qualification_fixture.QualificationTests.manage_page

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def values(self, name='甲公司'):
        return {field: name if field == '公司名称' else
                '2020-01-02' if field == '成立日期' else 'value_' + field
                for field in COMPANY_FIELDS}

    def test_all_fields_mouse_keyboard_and_context_copy(self):
        values = self.values()
        self.service.save_company(1, values)
        page = self.search_page()
        page.company.setCurrentIndex(page.company.findData(1))
        self.assertEqual(set(COMPANY_FIELDS), set(page.company_info.inputs))
        for field, editor in page.company_info.inputs.items():
            with self.subTest(field=field):
                self.assertTrue(editor.isReadOnly())
                self.assertEqual(values[field], editor.text())
                page.company_info.scroll.ensureWidgetVisible(editor)
                self.app.processEvents()
                QTest.mouseDClick(editor, Qt.LeftButton, pos=QPoint(10, editor.height() // 2))
                self.assertTrue(editor.selectedText())
                editor.selectAll()
                QTest.keyClick(editor, Qt.Key_C, Qt.ControlModifier)
                self.assertEqual(values[field], QGuiApplication.clipboard().text())
                menu = editor.createStandardContextMenu()
                copy = next(a for a in menu.actions() if 'Copy' in a.text())
                self.assertTrue(copy.isEnabled())
                QGuiApplication.clipboard().clear()
                copy.trigger()
                self.assertEqual(values[field], QGuiApplication.clipboard().text())
                menu.close()
        self.assertEqual(values['公司名称'], self.service.qualifications.company_info(1)['公司名称'])

    def test_company_change_clear_values_and_filter_selection_unchanged(self):
        self.service.save_company(1, self.values())
        page = self.search_page()
        page.selected_ids.add(self.a)
        page.company.setCurrentIndex(page.company.findData(2))
        self.assertEqual('乙公司', page.company_info.inputs['公司名称'].text())
        self.assertEqual('', page.company_info.inputs['统一社会信用代码'].text())
        page.search()
        self.assertEqual([self.b], [r['资质ID'] for r in page.model.rows])
        self.assertEqual({self.a}, page.selected_ids)
        page.company.setCurrentIndex(0)
        page.search()
        page.qualification_changed(page.model.index(next(i for i,r in enumerate(page.model.rows) if r['资质ID']==self.a), 1), None)
        self.assertEqual('甲公司', page.company_info.inputs['公司名称'].text())

    def test_edit_save_cancel_and_cross_page_refresh_preserve_links(self):
        search = self.search_page()
        page = self.manage_page()
        editor = page.company_info
        editor.reload(1)
        before = self.service.qualifications.get(self.a)
        editor.edit_button.click()
        editor.inputs['公司名称'].setText('取消的名字')
        editor.cancel_button.click()
        self.assertEqual('甲公司', editor.inputs['公司名称'].text())
        editor.edit_button.click()
        editor.inputs['公司名称'].setText('甲公司更新')
        editor.inputs['统一社会信用代码'].setText('TEST-CREDIT')
        editor.save_button.click()
        self.assertFalse(editor.editing)
        self.assertEqual('甲公司更新', self.service.qualifications.company_info(1)['公司名称'])
        self.assertEqual('乙公司', self.service.qualifications.company_info(2)['公司名称'])
        after = self.service.qualifications.get(self.a)
        self.assertEqual({k:v for k,v in before.items() if k!='公司名称'}, {k:v for k,v in after.items() if k!='公司名称'})
        search.refresh_companies()
        search.company.setCurrentIndex(search.company.findData(1))
        search.search()
        self.assertEqual('TEST-CREDIT', search.company_info.inputs['统一社会信用代码'].text())
        page.refresh_qualifications()
        self.assertEqual('甲公司更新', page.company_info.inputs['公司名称'].text())

    def test_validation_and_database_failure_are_atomic(self):
        values = self.values()
        for bad in ({**values, '成立日期':'2025-02-30'}, {**values,'成立日期':'20250101'}, {**values,'公司名称':None}):
            with self.assertRaises(ValueError):self.service.save_company(1, bad)
        with runtime_connection(self.db, write=True) as c:
            c.execute("CREATE TRIGGER fail_company BEFORE UPDATE ON 公司信息表 BEGIN SELECT RAISE(ABORT,'test failure'); END")
        page = self.manage_page()
        editor = page.company_info
        editor.edit_button.click()
        editor.inputs['公司名称'].setText('不能部分写入')
        editor.inputs['统一社会信用代码'].setText('FAIL')
        editor.save_button.click()
        self.assertTrue(editor.editing)
        self.assertIn('test failure', editor.error.text())
        self.assertEqual('甲公司', self.service.qualifications.company_info(1)['公司名称'])
        self.assertIsNone(self.service.qualifications.company_info(1)['统一社会信用代码'])

    def test_empty_database_explicit_initialization_no_duplicate_save(self):
        with runtime_connection(self.db, write=True) as c:
            c.execute('DELETE FROM 公司资质表');c.execute('DELETE FROM 公司信息表')
        search = self.search_page()
        self.assertTrue(all(not e.text() for e in search.company_info.inputs.values()))
        page = self.manage_page()
        editor = page.company_info
        self.assertFalse(editor.edit_button.isEnabled())
        editor.new_button.click()
        editor.inputs['公司名称'].setText('测试新公司')
        editor.save_button.click();editor.save_button.click()
        self.assertEqual(1, len(self.service.qualifications.companies()))
        self.assertEqual('测试新公司', editor.inputs['公司名称'].text())
        search.refresh_companies();search.search()
        self.assertEqual('测试新公司', search.company_info.inputs['公司名称'].text())
        with runtime_connection(self.db) as c:self.assertEqual(1,c.execute('pragma user_version').fetchone()[0])

    def test_read_failure_clears_old_company_and_disables_edit(self):
        page = self.manage_page()
        page.company_info.reload(1)
        self.assertEqual('甲公司', page.company_info.inputs['公司名称'].text())
        with patch.object(self.service.qualifications, 'company_info', side_effect=RuntimeError('test read failure')):
            page.company_info.reload(1)
        self.assertTrue(all(not e.text() for e in page.company_info.inputs.values()))
        self.assertFalse(page.company_info.edit_button.isEnabled())
        self.assertIn('test read failure', page.company_info.error.text())
        search = self.search_page()
        with patch.object(self.service.qualifications, 'company_info', side_effect=RuntimeError('test read failure')):
            search.refresh_company_info()
        self.assertTrue(all(not e.text() for e in search.company_info.inputs.values()))

    def test_unsaved_company_navigation_guard_and_edit_isolation(self):
        page = self.manage_page()
        editor = page.company_info
        editor.edit_button.click()
        editor.inputs['地址'].setText('待保存')
        self.assertFalse(page.edit_button.isEnabled())
        self.assertFalse(page.qualifications_view.isEnabled())
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):self.assertFalse(page.can_leave())
        editor.cancel_button.click()
        self.assertTrue(page.can_leave())
        self.assertTrue(page.qualifications_view.isEnabled())
        page.set_mode('edit')
        self.assertFalse(editor.isEnabled())

    def test_company_list_database_error_clears_both_pages(self):
        manage, search = self.manage_page(), self.search_page()
        with patch.object(self.service.qualifications,'companies',side_effect=RuntimeError('list unavailable')):
            manage.refresh_qualifications()
            search.refresh_companies()
        self.assertTrue(all(not e.text() for e in manage.company_info.inputs.values()))
        self.assertTrue(all(not e.text() for e in search.company_info.inputs.values()))
        self.assertIn('list unavailable', manage.company_info.error.text())

    def test_deleted_record_during_edit_is_not_reinserted(self):
        page = self.manage_page()
        editor = page.company_info
        editor.new_button.click()
        editor.inputs['公司名称'].setText('无资质公司')
        editor.save_button.click()
        target = editor.company_id
        editor.edit_button.click()
        editor.inputs['电话'].setText('TEST')
        with runtime_connection(self.db,write=True) as c:c.execute('DELETE FROM 公司信息表 WHERE 公司ID=?',(target,))
        editor.save_button.click()
        self.assertIn('不存在',editor.error.text())
        self.assertEqual(2,len(self.service.qualifications.companies()))

    def test_themes_layout_and_scroll_keep_fields_and_certificate_table_usable(self):
        manager = ThemeManager(self.app)
        self.addCleanup(lambda: manager.apply('light'))
        self.addCleanup(lambda: self.app.removeEventFilter(manager))
        search, manage = self.search_page(), self.manage_page()
        for theme in ('system','light','dark'):
            manager.apply(theme);self.app.processEvents()
            self.assertGreater(search.qualifications_view.viewport().height(), 100)
            self.assertGreater(search.company_info.inputs['公司名称'].height(), 15)
            last = manage.company_info.inputs['上一年基本信息']
            manage.company_info.scroll.ensureWidgetVisible(last)
            self.app.processEvents()
            self.assertGreater(last.height(),15)
            self.assertTrue(search.company_info.scroll.widgetResizable())
