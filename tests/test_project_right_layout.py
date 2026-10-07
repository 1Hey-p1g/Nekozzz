"""Phase 2E full right-column budget and overflow; TEMP fixtures, fake Word."""
import unittest
from PySide6.QtCore import Qt, QPoint, QPointF, QCoreApplication
from PySide6.QtGui import QWheelEvent, QImage, QColor
from services.pdf_import import RenderedPage
from services.projects import ProjectPersonnelEntry
from tests import test_project_info_layout as fixtures


class RightLayoutTests(unittest.TestCase):
    def setUp(self):
        self.fixture = t = fixtures.ProjectInfoLayoutTests()
        t.setUp()
        self.addCleanup(t.doCleanups)
        self.page = t.page
        self.facts = t.fixture.fixture

    def pump(self):
        self.fixture.pump()

    def data(self, people, images):
        f = self.facts
        if images:
            f.publisher.save_pages((f.a,'合同'),tuple(RenderedPage(i+1,f.pages[0].path) for i in range(images)),
                                   replace=bool(f.service.projects.attachments(f.a,'合同')))
            # Several attachment types as well as several pages in one type.
            for i in range(min(images,6)-1):
                f.publisher.save_pages((f.a,f'类型{i}'),f.pages[:1],
                                       replace=bool(f.service.projects.attachments(f.a,f'类型{i}')))
        self.fixture.people(people)
        self.pump()

    def assert_all_sections(self):
        p = self.page
        self.fixture.assert_readable()
        for view,rows in ((p.types_view,3),(p.attachments_view,2)):
            required = sum(view.rowHeight(i) for i in range(min(rows,view.model().rowCount())))
            self.assertGreaterEqual(view.viewport().height(),required)
            self.assertGreaterEqual(view.height(),view.minimumHeight())
        self.assertGreaterEqual(p.preview.height(),p.preview.minimumHeight())
        layout = p.right.layout()
        margins = layout.contentsMargins()
        total = margins.top()+margins.bottom()+layout.spacing()*(layout.count()-1)
        total += sum(layout.itemAt(i).widget().minimumHeight() for i in range(layout.count()))
        self.assertGreaterEqual(p.right.height(),total)
        if total > p.right_scroll.viewport().height():
            self.assertGreater(p.right_scroll.verticalScrollBar().maximum(),0)
            p.right_scroll.ensureWidgetVisible(p.preview)
            self.pump()
            position = p.preview.mapTo(p.right_scroll.viewport(),p.preview.rect().bottomLeft())
            self.assertLessEqual(position.y(),p.right_scroll.viewport().height())
        self.assertEqual(0,p.right_scroll.horizontalScrollBar().maximum())

    def test_data_zero_one_three_six_ten_all_sections_actual_heights(self):
        # Begin empty, then grow both relation and attachment content.
        self.data(0,0)
        self.assert_all_sections()
        for count in (1,3,6,10):
            with self.subTest(count=count):
                self.data(count,count)
                self.assert_all_sections()

    def test_shrink_expand_restore_and_preview_primary_elastic_space(self):
        self.data(6,6)
        self.page.resize(1050,700)
        self.pump()
        self.assert_all_sections()
        normal = self.page.size(),self.page.preview.height(),self.page.info_view.viewport().height()
        self.page.resize(1000,600)
        self.pump()
        self.assert_all_sections()
        self.page.resize(1350,1500)
        self.pump()
        self.assert_all_sections()
        self.assertGreater(self.page.preview.height(),normal[1])
        self.assertEqual(self.page.info_view.viewport().height(),normal[2])
        self.page.resize(normal[0])
        self.pump()
        self.assert_all_sections()

    def test_thirty_people_many_images_do_not_grow_page_minimum(self):
        self.data(10,10)
        minimum = self.page.minimumSizeHint()
        content_minimum = self.page.right.minimumSizeHint().height()
        size = self.page.size()
        # Same bounded first rows, but substantially more content in both inner tables.
        f = self.facts
        f.publisher.save_pages((f.a,'合同'),tuple(RenderedPage(i+1,f.pages[0].path) for i in range(40)),replace=True)
        f.service.save(f.a,{'项目名称':'A配网'},personnel=[ProjectPersonnelEntry(None,1,f'职务{i}') for i in range(30)])
        self.fixture.fixture.select(self.fixture.fixture.c)
        self.fixture.fixture.select(f.a)
        self.pump()
        self.assert_all_sections()
        self.assertEqual(minimum,self.page.minimumSizeHint())
        self.assertEqual(content_minimum,self.page.right.minimumSizeHint().height())
        self.assertEqual(size,self.page.size())
        self.assertGreater(self.page.personnel_view.verticalScrollBar().maximum(),0)
        self.assertGreater(self.page.attachments_view.verticalScrollBar().maximum(),0)

    def test_inner_wheel_priority_outer_scroll_access(self):
        self.data(10,10)
        p = self.page
        for view in (p.info_view,p.personnel_view,p.types_view,p.attachments_view):
            with self.subTest(view=view):
                p.right_scroll.ensureWidgetVisible(view)
                self.pump()
                view.verticalScrollBar().setValue(0)
                outer = p.right_scroll.verticalScrollBar().value()
                viewport = view.viewport()
                position = viewport.rect().center()
                event = QWheelEvent(QPointF(position),QPointF(viewport.mapToGlobal(position)),QPoint(),
                    QPoint(0,-120),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
                QCoreApplication.sendEvent(viewport,event)
                self.pump()
                self.assertGreater(view.verticalScrollBar().value(),0)
                self.assertEqual(outer,p.right_scroll.verticalScrollBar().value())
                # At either inner boundary the outer scrollbar remains operable.
                view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())
                p.right_scroll.verticalScrollBar().setValue(p.right_scroll.verticalScrollBar().maximum())
                self.assertEqual(p.right_scroll.verticalScrollBar().value(),p.right_scroll.verticalScrollBar().maximum())

    def test_image_switch_and_no_image_placeholder(self):
        self.data(3,3)
        p,f = self.page,self.facts
        self.assertIsNotNone(p.preview._pixmap)
        self.assertFalse(p.preview.pixmap().isNull())
        red = QImage(16,24,QImage.Format_RGB32)
        red.fill(QColor('red'))
        path = f.root/'red.jpg'
        red.save(str(path),'JPEG')
        f.publisher.save_pages((f.a,'合同'),(RenderedPage(1,f.pages[0].path),RenderedPage(2,path)),replace=True)
        p.project_changed(p.task_list.currentItem(),None)
        self.pump()
        p.attachments_view.selectRow(1)
        self.pump()
        pixel = p.preview._pixmap.toImage().pixelColor(0,0)
        self.assertGreater(pixel.red(),pixel.blue())
        self.assertLessEqual(p.preview.pixmap().width(),p.preview.width())
        self.assertLessEqual(p.preview.pixmap().height(),p.preview.height())
        self.fixture.fixture.select(self.fixture.fixture.c)
        self.pump()
        self.assertIsNone(p.preview._pixmap)
        self.assertGreaterEqual(p.preview.height(),p.preview.minimumHeight())


if __name__=='__main__':
    unittest.main()
