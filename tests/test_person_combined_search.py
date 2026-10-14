"""Combined same-certificate search, isolated V1 database and cached GUI."""
import unittest
from datetime import date, timedelta
from unittest.mock import patch
from tests import test_development_094 as development
from database.runtime import runtime_connection


class CombinedSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        development.Development094Tests.setUpClass()

    def setUp(self):
        self.fixture = f = development.Development094Tests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.repo = f.people.people
        today = date.today()
        with runtime_connection(f.db, write=True) as c:
            c.execute('DELETE FROM 人员证书表')
            c.execute('INSERT INTO 人员表(人员ID,姓名) VALUES(1,?)', ('无证',))
            c.executemany('INSERT INTO 人员证书表(证书ID,人员ID,证书名称,有效期) VALUES(?,?,?,?)', [
                (10,2,'建造师', (today+timedelta(days=30)).isoformat()),
                (2,2,'安全员', (today-timedelta(days=1)).isoformat()),
                (11,2,'建造师长期', None),
                (20,10,'安全员', today.isoformat()),
                (21,10,'临界', (today+timedelta(days=29)).isoformat()),
                (22,10,'特殊%_\\证', ''),
            ])

    def ids(self, name='', certificate='', status=''):
        return [r['人员ID'] for r in self.repo.search(name, certificate, certificate_status=status)]

    def test_empty_and_name_order(self):
        self.assertEqual([1,2,10], self.ids())
        self.assertEqual([2], self.ids('乙'))
        self.assertEqual([], self.ids("' OR 1=1 --"))

    def test_certificate_name_and_no_duplicates(self):
        self.assertEqual([2], self.ids(certificate='建造'))
        self.assertEqual([2,10], self.ids(certificate='安全'))
        self.assertEqual([], self.ids(certificate='不存在'))

    def test_status_and_boundaries(self):
        self.assertEqual([2], self.ids(status='有效'))
        self.assertEqual([10], self.ids(status='即将到期'))
        self.assertEqual([2], self.ids(status='已过期'))
        self.assertEqual([2], self.ids(certificate='长期',status='有效'))
        self.assertEqual([], self.ids(certificate='特殊',status='有效'))

    def test_same_certificate_and_three_conditions(self):
        self.assertEqual([], self.ids('乙','建造','已过期'))
        self.assertEqual([2], self.ids('乙','安全','已过期'))
        self.assertEqual([], self.ids('甲','安全','已过期'))

    def test_literal_special_characters_and_invalid_status(self):
        self.assertEqual([10], self.ids(certificate='%_\\'))
        with self.assertRaises(ValueError):
            self.ids(status='unknown')

    def test_one_query_and_shared_expiry_rule(self):
        statements=[]
        original=runtime_connection
        from contextlib import contextmanager
        @contextmanager
        def traced(*args, **kwargs):
            with original(*args, **kwargs) as c:
                c.set_trace_callback(statements.append)
                yield c
        with patch('repositories.person_repository.runtime_connection',traced), patch(
                'services.people.expiry_status',return_value='已过期') as rule:
            self.assertEqual([2],self.ids(certificate='建造',status='已过期'))
            self.assertTrue(rule.called)
        self.assertEqual(1,sum(s.startswith('SELECT 人员ID') for s in statements))

    def test_gui_cached_filters_task_selection_and_clear(self):
        f=self.fixture
        w=f.window()
        p=w.person_word_page
        self.assertEqual('',p.certificate_status_filter.currentData())
        p.add_person(p.people_model.index(1,0))
        p.job.item(2).selected_certificate_ids.add(10)
        p.view_person(2)
        p.name_filter.setText('甲')
        p.certificate_name_filter.setText('安全')
        p.certificate_status_filter.setCurrentIndex(2)
        p.certificate_name_filter.returnPressed.emit()
        self.assertEqual([10],[r['人员ID'] for r in p.people_model.rows])
        self.assertIsNone(p.viewed_person_id)
        self.assertEqual([],p.certificate_model.rows)
        self.assertEqual([],p.attachment_model.rows)
        self.assertEqual([2],p.task_list.person_ids())
        self.assertEqual({10},p.job.item(2).selected_certificate_ids)
        w.navigate('about_page')
        w.navigate('person_word_page')
        self.assertIs(p,w.person_word_page)
        self.assertEqual('甲',p.name_filter.text())
        self.assertEqual('安全',p.certificate_name_filter.text())
        self.assertEqual('即将到期',p.certificate_status_filter.currentData())
        p.clear_filters_button.click()
        self.assertEqual([1,2,10],[r['人员ID'] for r in p.people_model.rows])
        self.assertEqual([2],p.task_list.person_ids())
        p.view_person(2)
        self.assertEqual([2,10,11],[r['证书ID'] for r in p.certificate_model.rows])

    def test_multiple_tasks_keep_order_and_checks_on_empty_result(self):
        w=self.fixture.window()
        p=w.person_word_page
        p.add_person(p.people_model.index(1,0))
        p.add_person(p.people_model.index(2,0))
        p.job.item(2).selected_certificate_ids.add(10)
        p.job.item(10).selected_certificate_ids.add(20)
        p.job.reorder([10,2])
        p._refresh_task_list(select_id=10)
        p.certificate_name_filter.setText('不存在')
        p.search_people()
        self.assertEqual([],p.people_model.rows)
        self.assertEqual([10,2],p.task_list.person_ids())
        self.assertEqual({10},p.job.item(2).selected_certificate_ids)
        self.assertEqual({20},p.job.item(10).selected_certificate_ids)
        p.clear_search_filters()
        self.assertEqual([10,2],p.task_list.person_ids())
