"""Phase 2B layout/focus regression; TEMP fixtures, no business writes or COM."""
import unittest
from unittest.mock import patch
from PySide6.QtCore import QEvent, Qt, QCoreApplication
from PySide6.QtGui import QPalette, QColor, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMainWindow, QScrollArea
from tests import test_project_personnel as fixtures
from gui.main_window import STYLE


class PersonnelGuiTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.ProjectPersonnelTests()
        fixture.setUpClass()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.app = fixture.app
        self.page = fixture.page()
        self.window = QMainWindow()
        self.window.setStyleSheet(STYLE)
        self.window.setCentralWidget(self.page)
        self.window.resize(1050,700)
        self.window.show()
        self.addCleanup(self.window.close)
        self.page.set_mode('edit')
        self.editor = self.page.personnel
        self.pump()

    def pump(self):
        self.app.processEvents()
        self.app.processEvents()

    def add_to(self, count):
        while len(self.editor.rows)<count:
            self.editor.add_entry()
        self.pump()

    def test_normal_three_rows_resize_and_restore(self):
        self.add_to(10)
        e = self.editor
        row_height = e.rows[0][1].sizeHint().height()
        expected = row_height*3 + e.row_layout.spacing()*2
        self.assertGreaterEqual(e.scroll.viewport().height(),expected)
        normal = e.scroll.viewport().height()
        self.window.resize(1350,1600)
        self.pump()
        self.assertGreaterEqual(e.scroll.viewport().height(),normal)
        self.window.resize(900,500)
        self.pump()
        self.assertGreaterEqual(e.scroll.viewport().height(),expected)
        self.window.resize(1050,700)
        self.pump()
        self.assertGreaterEqual(e.scroll.viewport().height(),expected)

    def test_thirty_rows_do_not_expand_main_window_minimum(self):
        self.add_to(10)
        size, minimum = self.window.size(), self.window.minimumSizeHint().height()
        self.add_to(30)
        self.assertEqual(self.window.size(),size)
        self.assertEqual(self.window.minimumSizeHint().height(),minimum)
        self.assertGreater(self.editor.scroll.verticalScrollBar().maximum(),0)
        self.assertTrue(self.editor.add_button.isEnabled())

    def test_eleventh_row_activated_and_scrolled_into_view(self):
        self.add_to(10)
        e = self.editor
        e.scroll.verticalScrollBar().setValue(0)
        with patch.object(e.scroll,'ensureWidgetVisible',wraps=e.scroll.ensureWidgetVisible) as reveal:
            e.add_button.click()
            self.pump()
            row = e.rows[-1][1]
            self.assertIs(e.active_row,row)
            self.assertTrue(row.property('active'))
            reveal.assert_called_with(row,0,e.row_layout.spacing())
        position = row.mapTo(e.scroll.viewport(),row.rect().topLeft())
        self.assertGreaterEqual(position.y(),0)
        self.assertLessEqual(position.y()+row.height(),e.scroll.viewport().height())

    def test_role_focus_person_click_and_editable_line_focus_only_one_active(self):
        self.add_to(5)
        e = self.editor
        dirty = self.page.dirty
        with patch.object(self.page,'mark_dirty') as dirty_from_visual:
            QCoreApplication.sendEvent(e.rows[1][2],QEvent(QEvent.FocusIn))
            self.assertIs(e.active_row,e.rows[1][1])
            person = e.rows[4][3]
            QTest.mouseClick(person,Qt.LeftButton)
            person.hidePopup()
            self.assertIs(e.active_row,e.rows[4][1])
            self.assertFalse(e.rows[1][1].property('active'))
            QCoreApplication.sendEvent(e.rows[2][2].lineEdit(),QEvent(QEvent.FocusIn))
            self.assertIs(e.active_row,e.rows[2][1])
            self.assertEqual(sum(bool(row.property('active')) for _,row,_,_,_ in e.rows),1)
            dirty_from_visual.assert_not_called()
        self.assertEqual(self.page.dirty,dirty)

    def test_active_delete_reload_and_view_clear_state(self):
        self.add_to(11)
        e = self.editor
        e.activate_row(e.rows[-1][1])
        e.rows[-1][-1].click()
        self.pump()
        self.assertEqual(len(e.rows),10)
        self.assertTrue(e.active_row is None or any(row is e.active_row for _,row,_,_,_ in e.rows))
        e.activate_row(e.rows[0][1])
        self.page.load(self.page.service.projects.get(self.page.project_id))
        self.assertIsNone(e.active_row)
        self.page.set_mode('view')
        QCoreApplication.sendEvent(e.rows[0][2].lineEdit(),QEvent(QEvent.FocusIn))
        self.assertIsNone(e.active_row)
        self.assertFalse(e.add_button.isEnabled())

    def test_palette_driven_active_colors_change_with_palette(self):
        row = self.editor.rows[0][1]
        self.editor.activate_row(row)
        for accent in (QColor(Qt.darkBlue), QColor(Qt.cyan)):
            palette = QPalette(row.palette())
            palette.setColor(QPalette.Active,QPalette.Highlight,accent)
            row.setPalette(palette)
            background,border = row.active_colors()
            self.assertEqual(background.rgb(),row.palette().color(QPalette.Active,QPalette.Highlight).rgb())
            self.assertEqual(border.rgb(),background.rgb())
            self.assertLess(background.alpha(),border.alpha())
            self.assertLess(border.alpha(),255)
            self.assertTrue(row.property('active'))

    def test_internal_wheel_scroll_and_external_page_remains_scrollable(self):
        self.add_to(30)
        e = self.editor
        outer = next(s for s in self.page.findChildren(QScrollArea) if s is not e.scroll)
        e.scroll.verticalScrollBar().setValue(0)
        outer_before = outer.verticalScrollBar().value()
        viewport = e.scroll.viewport()
        position = viewport.rect().center()
        from PySide6.QtCore import QPoint, QPointF
        wheel = QWheelEvent(QPointF(position),QPointF(viewport.mapToGlobal(position)),QPoint(),
                            QPoint(0,-120),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
        QCoreApplication.sendEvent(viewport,wheel)
        self.pump()
        self.assertGreater(e.scroll.verticalScrollBar().value(),0)
        self.assertEqual(outer.verticalScrollBar().value(),outer_before)
        self.assertGreater(outer.verticalScrollBar().maximum(),0)
        outer.verticalScrollBar().setValue(outer.verticalScrollBar().maximum())
        self.assertEqual(outer.verticalScrollBar().value(),outer.verticalScrollBar().maximum())


if __name__=='__main__':
    unittest.main()
