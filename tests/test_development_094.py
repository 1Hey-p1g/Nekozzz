"""v0.9.4 startup, lazy navigation, ID ordering and geometry regressions."""
import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton
from database.initializer import create_empty_database
from database.runtime import runtime_connection
from gui.main_window import build_main_window
from gui.common import RowsModel
from services.people import PeopleService, expiry_status
from services.qualifications import QualificationService
from services.projects import ProjectService
from services.award_finance import AwardService, FinanceService
from services.settings import PdfSettings, SettingsService
from gui.window_geometry import restore_window_geometry

class Development094Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='Nekozzz_v094_')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.db=self.root/'data.db'
        create_empty_database(self.db)
        self.settings=SettingsService(self.root/'settings.json')
        self.people=PeopleService(self.db)
        with runtime_connection(self.db,write=True) as c:
            c.executemany('INSERT INTO 人员表(人员ID,姓名) VALUES(?,?)',[(10,'甲'),(2,'乙')])
            c.executemany('INSERT INTO 人员证书表(证书ID,人员ID,证书名称,有效期) VALUES(?,2,?,?)',[(10,'长期',None),(2,'过期',(date.today()-timedelta(days=1)).isoformat()),(1,'近期',(date.today()+timedelta(days=10)).isoformat()),(11,'未来','2099-12-31')])
            c.executemany('INSERT INTO 公司信息表(公司ID,公司名称) VALUES(?,?)',[(5,'乙公司'),(1,'甲公司')])
            c.executemany('INSERT INTO 公司资质表(资质ID,公司ID,资质证书名称) VALUES(?,?,?)',[(2,5,'乙证'),(11,1,'甲证十一'),(10,1,'甲证十')])
            c.executemany('INSERT INTO 公司业绩表(业绩ID,项目名称) VALUES(?,?)',[(10,'甲项目'),(2,'乙项目')])
            c.executemany('INSERT INTO 人员业绩表(ID,人员ID,业绩ID,担任角色) VALUES(?,?,?,?)',[(10,2,2,'项目负责人'),(5,10,2,'施工员'),(2,2,10,'技术负责人')])
            c.executemany('INSERT INTO 获奖工程表(获奖ID,业绩ID,获奖名称,获奖年份) VALUES(?,2,?,?)',[(10,'甲奖','2030'),(2,'乙奖','2020')])
            c.executemany('INSERT INTO 财务报告表(年度ID,财务报告年度) VALUES(?,?)',[(10,'2030'),(2,'2020')])

    def window(self):
        w=build_main_window(self.people,self.db,settings_service=self.settings)
        self.addCleanup(w.close)
        return w

    def test_first_screen_only_and_no_old_page(self):
        w=self.window()
        self.assertEqual({'person_word_page'},set(w.created_pages))
        self.assertIs(w.workspace.currentWidget(),w.person_word_page)
        self.assertFalse(hasattr(w,'search_page'))
        self.assertEqual([],w.findChildren(QPushButton,'personModeButton'))
        self.assertIn('0.9.4',w.windowTitle())
        button=w.findChild(QPushButton,'navPersonSearch')
        for _ in range(3):
            button.click()
            self.assertTrue(button.isChecked())
        self.assertEqual({'person_word_page'},set(w.created_pages))

    def test_factory_cache_navigation_filters_and_tasks(self):
        w=self.window()
        p=w.person_word_page
        p.name_filter.setText('乙');p.search_people();p.add_person(p.people_model.index(0,0))
        p.certificate_model.setData(p.certificate_model.index(0,0),Qt.Checked,Qt.CheckStateRole)
        p.certificates_view.setCurrentIndex(p.certificate_model.index(2,1))
        for _ in range(3):
            w.navigate('about_page');w.navigate('settings_page');w.navigate('person_word_page')
        self.assertIs(p,w.person_word_page)
        self.assertEqual('乙',p.name_filter.text())
        self.assertEqual({1},p.job.item(2).selected_certificate_ids)
        self.assertEqual(10,p.certificate_model.active_id)
        self.assertEqual({'person_word_page','about_page','settings_page'},set(w.created_pages))

    def test_all_navigation_cached_and_shared_office_factory(self):
        w=self.window()
        for name in list(w._page_factories):w.navigate(name)
        ids={name:id(page) for name,page in w.created_pages.items()}
        for name in list(w._page_factories):w.navigate(name)
        self.assertEqual(ids,{name:id(page) for name,page in w.created_pages.items()})
        outputs=[w.person_word_page,w.project_search_page,w.qualification_search_page,w.award_search_page,w.finance_search_page,w.person_autofill_page]
        factories=[p.output_service.word_factory for p in outputs]
        self.assertTrue(all(factory is factories[0] for factory in factories))
        self.assertIs(factories[0].settings_service,self.settings)
        for theme in ('system','light','dark'):
            self.app.theme_manager.apply(theme)
            w.navigate('about_page')
            self.assertIs(w.workspace.currentWidget(),w.about_page)
        self.app.theme_manager.apply('system')

    def test_dirty_guard_does_not_create_target_page(self):
        w=self.window();w.navigate('manage_page')
        with patch.object(w.manage_page,'can_leave',return_value=False):
            w.navigate('project_manage_page')
            self.assertNotIn('project_manage_page',w.created_pages)
            self.assertIs(w.workspace.currentWidget(),w.manage_page)
            self.assertFalse(w.prepare_restore())
            self.assertFalse(w.close())
        self.assertTrue(w.prepare_restore())
        from threading import Thread
        errors=[]
        def background_access():
            try:
                w.get_page('project_search_page')
            except RuntimeError as error:
                errors.append(str(error))
        worker=Thread(target=background_access)
        worker.start();worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(['业务页面必须在 GUI 主线程创建'],errors)
        self.assertNotIn('project_search_page',w.created_pages)

    def test_restore_and_busy_do_not_save_or_create_pages(self):
        w=self.window()
        self.settings.save(replace(PdfSettings(),writer_target='wps'))
        before=self.settings.path.read_bytes()
        w._data_operation_running=True
        w.navigate('manage_page')
        self.assertNotIn('manage_page',w.created_pages)
        self.assertFalse(w.close())
        w._data_operation_running=False;w._restore_completed=True
        w.close()
        self.assertEqual(before,self.settings.path.read_bytes())

    def test_certificate_expiry_columns_and_id_order(self):
        w=self.window();p=w.person_word_page
        p.add_person(p.people_model.index(0,0))
        self.assertEqual(['选择','证书类型','证书名称','证书编号','有效期','状态'],[c[0] for c in p.certificate_model.columns])
        self.assertEqual([1,2,10,11],[r['证书ID'] for r in p.certificate_model.rows])
        self.assertEqual([expiry_status(r['有效期']) for r in p.certificate_model.rows],[r['状态'] for r in p.certificate_model.rows])
        self.assertEqual('长期有效',p.certificate_model.rows[2]['状态'])
        self.assertIn('过期',p.certificate_model.rows[1]['状态'])
        self.assertIn('即将',p.certificate_model.rows[0]['状态'])

    def test_company_one_default_uses_fk_and_keeps_user_filter(self):
        w=self.window();w.navigate('qualification_search_page');p=w.qualification_search_page
        self.assertEqual(1,p.company.currentData())
        self.assertEqual([10,11],[r['资质ID'] for r in p.model.rows])
        p.company.setCurrentIndex(p.company.findData(5))
        self.assertEqual([2],[r['资质ID'] for r in p.model.rows])

        with patch.object(p.service.qualifications,'companies',side_effect=OSError('retry fixture')):
            p.refresh_companies();p.search()
            self.assertEqual([],p.model.rows)
            self.assertFalse(p.company.isEnabled())
        p.refresh_companies();p.search()
        self.assertEqual(5,p.company.currentData())
        self.assertEqual([2],[r['资质ID'] for r in p.model.rows])
        p.name_input.setText('乙');p.search();p.selected_ids.add(2)
        w.navigate('about_page');w.navigate('qualification_search_page')
        self.assertEqual(5,p.company.currentData())
        self.assertEqual('乙',p.name_input.text())
        self.assertEqual({2},p.selected_ids)
        self.assertEqual([2],[r['资质ID'] for r in p.model.rows])

    def test_missing_company_one_does_not_show_other_company(self):
        with runtime_connection(self.db,write=True) as c:
            c.execute('DELETE FROM 公司资质表 WHERE 公司ID=1');c.execute('DELETE FROM 公司信息表 WHERE 公司ID=1')
        p=self.window().qualification_search_page
        self.assertEqual(1,p.company.currentData())
        self.assertEqual([],p.model.rows)
        self.assertTrue(all(not x.text() for x in p.company_info.inputs.values()))
        p.company.setCurrentIndex(p.company.findData(5))
        self.assertEqual([2],[r['资质ID'] for r in p.model.rows])

    def test_company_one_without_certificates_is_empty(self):
        with runtime_connection(self.db,write=True) as c:c.execute('DELETE FROM 公司资质表 WHERE 公司ID=1')
        p=self.window().qualification_search_page
        self.assertEqual([],p.model.rows)
        self.assertEqual(1,p.company.currentData())

    def test_company_list_failure_does_not_leak_all_companies(self):
        source=QualificationService(self.db)
        with patch.object(source.qualifications,'companies',side_effect=OSError('test read failure')):
            w=build_main_window(self.people,self.db,settings_service=self.settings,qualification_service=source)
            self.addCleanup(w.close)
            p=w.qualification_search_page
            self.assertEqual([],p.model.rows)
            self.assertIn('test read failure',p.error_label.text())

    def test_entity_and_relation_repositories_numeric_ids(self):
        project=ProjectService(self.db);qual=QualificationService(self.db)
        for rows,key in ((self.people.people.search(),'人员ID'),(project.projects.search(),'业绩ID'),(qual.qualifications.companies(),'公司ID'),(qual.qualifications.search(),'资质ID'),(AwardService(self.db).search(),'获奖ID'),(FinanceService(self.db).search(),'年度ID')):
            ids=[r[key] for r in rows]
            self.assertEqual(sorted(ids),ids)
        self.assertEqual([2,10],[r['ID'] for r in self.people.people.projects(2)])
        self.assertEqual([5,10],[r['relation_id'] for r in project.projects.project_personnel(2)])

    def test_child_display_order_and_idless_auxiliary_order(self):
        model=RowsModel([('页','备注')])
        model.set_rows([{'ID':10,'备注':1},{'ID':2,'备注':2}])
        self.assertEqual([2,10],[r['ID'] for r in model.rows])
        model.set_rows([{'备注':10},{'备注':2}])
        self.assertEqual([10,2],[r['备注'] for r in model.rows])

    def test_geometry_roundtrip_preserves_other_settings(self):
        self.settings.save(replace(PdfSettings(),writer_target='wps',theme='dark'))
        w=self.window();w.setGeometry(40,40,650,500);w.close()
        saved=self.settings.load()
        self.assertTrue(saved.window_geometry)
        self.assertEqual(('wps','dark'),(saved.writer_target,saved.theme))
        second=self.window()
        self.assertGreater(second.width(),0);self.assertGreater(second.height(),0)
        self.assertTrue(any(s.availableGeometry().intersects(second.frameGeometry()) for s in self.app.screens()))
        self.assertEqual(saved.window_geometry,self.settings.load().window_geometry)

    def test_invalid_geometry_does_not_reset_preferences(self):
        w=self.window();default=w.geometry()
        for value in ('not base64!',base64.b64encode(b'not Qt geometry').decode()):
            self.settings.save(replace(PdfSettings(),writer_target='wps',window_geometry=value))
            self.assertFalse(restore_window_geometry(w,self.settings))
            self.assertEqual(default.size(),w.geometry().size())
            self.assertEqual('wps',self.settings.load().writer_target)

    def test_offscreen_and_maximized_geometry(self):
        w=self.window();w.setGeometry(100000,100000,600,500);w.close()
        second=self.window()
        self.assertTrue(any(s.availableGeometry().intersects(second.frameGeometry()) for s in self.app.screens()))
        second.showMaximized();self.app.processEvents();second.close()
        third=self.window();self.assertTrue(third.isMaximized())

    def test_geometry_write_error_does_not_crash_close(self):
        w=self.window()
        with patch.object(self.settings,'save',side_effect=OSError('read-only fixture')):
            w.close()
        self.assertIn('read-only fixture',w.geometry_persistence_error)

    def test_fresh_process_has_no_heavy_imports_or_old_page(self):
        code='''import os,sys,tempfile,pathlib
os.environ['QT_QPA_PLATFORM']='offscreen'
from database.initializer import create_empty_database
from services.settings import SettingsService
from services.people import PeopleService
from gui.main_window import build_main_window
from PySide6.QtWidgets import QApplication
app=QApplication([])
with tempfile.TemporaryDirectory() as d:
 p=pathlib.Path(d)/'db'; create_empty_database(p)
 w=build_main_window(PeopleService(p),p,settings_service=SettingsService(pathlib.Path(d)/'settings.json'))
 assert list(w.created_pages)==['person_word_page']
 assert not any(n in sys.modules for n in ['openpyxl','pymupdf','pyodbc','gui.person_search'])
 w.navigate('settings_page');w.navigate('manage_page')
 assert not any(n in sys.modules for n in ['openpyxl','pymupdf','pyodbc','gui.person_search'])
 w.close()
'''
        result=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True,timeout=25)
        self.assertEqual(0,result.returncode,result.stderr)
