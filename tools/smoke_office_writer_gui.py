"""Explicit real GUI/COM smoke, only new documents and synthetic local data.

Requires both Word and WPS already running. Never launches/quits them or writes
an existing document. Intended for developer verification, not app runtime.
"""
from dataclasses import replace
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QStackedWidget
from win32com.client import GetActiveObject
from database.initializer import create_empty_database
from database.runtime import runtime_connection
from gui.main_window import build_main_window
from gui.common import ImagePreview
from services.people import PeopleService
from services.projects import ProjectService
from services.qualifications import QualificationService
from services.award_finance import AwardService, FinanceService
from services.settings import SettingsService
from services.office_writer import OfficeWriterConnector
from services.person_word import PersonWordOutputService
from services.project_word import ProjectWordOutputService
from services.qualification_word import QualificationWordOutputService
from services.report_word import ReportWordOutputService
from services.autofill.person_service import PersonAutoFillService
from services.attachments import (CertificateAttachmentService, ProjectAttachmentService,
    QualificationAttachmentService, AwardAttachmentService, FinanceAttachmentService)
from services.data_management import DataManagementService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=('word', 'wps', 'both'), default='both')
    parser.add_argument('--interactive', action='store_true', help='Open test-owned Nekozzz GUI for manual operation; no automatic Office writes.')
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    out = ROOT / 'report/wps_writer_support' / datetime.now().strftime('gui_smoke_%Y%m%d_%H%M%S_%f')
    out.mkdir(parents=True)
    data = out / 'synthetic_data'
    data.mkdir()
    db = data / 'test.db'
    create_empty_database(db)
    images = data / 'Images'
    images.mkdir()
    for i in range(1, 5):
        image = QImage(240, 160, QImage.Format_RGB32)
        image.fill(QColor(('red', 'blue', 'green', 'orange')[i-1]))
        assert image.save(str(images / f'{i}.jpg'), 'JPEG')
    with runtime_connection(db, write=True) as c:
        for i in range(1, 5):
            c.execute('INSERT INTO 人员表(人员ID,姓名,毕业院校,专业) VALUES(?,?,?,?)', (i, f'测试人员{i}', '合成学校', '合成专业'))
            c.execute('INSERT INTO 人员证书表(证书ID,人员ID,证书名称,证书类型) VALUES(?,?,?,?)', (i*100+1, i, f'合成证书{i}', '测试证'))
            c.execute('INSERT INTO 人员证书图表(ID,证书ID,路径,备注) VALUES(?,?,?,?)', (i, i*100+1, f'Images/{i}.jpg', '1'))
        c.execute("INSERT INTO 公司信息表(公司ID,公司名称) VALUES(1,'合成测试公司')")
        for i in (1, 2):
            c.execute('INSERT INTO 公司业绩表(业绩ID,项目名称) VALUES(?,?)', (i, f'合成工程{i}'))
            c.execute('INSERT INTO 公司业绩图表(ID,业绩ID,文件类型,路径,备注) VALUES(?,?,?,?,?)', (i, i, '合成合同', f'Images/{i}.jpg', 1))
            c.execute('INSERT INTO 公司资质表(资质ID,公司ID,资质证书名称) VALUES(?,1,?)', (i, f'合成资质{i}'))
            c.execute('INSERT INTO 公司资质图表(ID,资质ID,路径,备注) VALUES(?,?,?,?)', (i, i, f'Images/{i}.jpg', '1'))
            c.execute('INSERT INTO 获奖工程表(获奖ID,业绩ID,获奖名称) VALUES(?,?,?)', (i, i, f'合成奖项{i}'))
            c.execute('INSERT INTO 获奖工程图表(ID,获奖ID,路径,备注) VALUES(?,?,?,?)', (i, i, f'Images/{i}.jpg', 1))
            c.execute('INSERT INTO 财务报告表(年度ID,财务报告年度) VALUES(?,?)', (i, str(2023+i)))
            c.execute('INSERT INTO 财务报告图表(ID,年度ID,路径,备注) VALUES(?,?,?,?)', (i, i, f'Images/{i}.jpg', '1'))
    settings = SettingsService(data / 'settings.json')
    connector = OfficeWriterConnector(settings)
    people, projects = PeopleService(db), ProjectService(db)
    qualifications = QualificationService(db)
    award, finance = AwardService(db), FinanceService(db)
    window = build_main_window(people, db, settings_service=settings,
        attachment_service=CertificateAttachmentService(db, data_root=data),
        project_attachment_service=ProjectAttachmentService(db, data_root=data),
        qualification_attachment_service=QualificationAttachmentService(db, data_root=data),
        award_attachment_service=AwardAttachmentService(db, data_root=data),
        finance_attachment_service=FinanceAttachmentService(db, data_root=data),
        data_management_service=DataManagementService(db, data_root=data, settings_path=settings.path),
        person_word_service=PersonWordOutputService(people, data_root=data, word_factory=connector),
        project_service=projects, project_word_service=ProjectWordOutputService(projects.projects, data_root=data, word_factory=connector),
        qualification_service=qualifications, qualification_word_service=QualificationWordOutputService(qualifications.qualifications, data_root=data, word_factory=connector),
        award_service=award, finance_service=finance,
        award_word_service=ReportWordOutputService(award.repository, data_root=data, word_factory=connector),
        finance_word_service=ReportWordOutputService(finance.repository, data_root=data, word_factory=connector))
    # Audit-only test-root injection, same production AutoFill service/connector.
    window.person_autofill_page.output_service = PersonAutoFillService(people, data_root=data, word_factory=connector)
    for preview in window.findChildren(ImagePreview):
        preview.data_root = data
    window.show()
    app.processEvents()
    if args.interactive:
        print('Synthetic test data only:', data, flush=True)
        print('Open Word/WPS yourself, select Settings > insertion target, and operate the GUI.', flush=True)
        return app.exec()
    dialogs = []
    timer = QTimer()
    def record_dialog():
        for widget in app.topLevelWidgets():
            if isinstance(widget, QMessageBox) and widget.isVisible():
                dialogs.append(widget.text())
                widget.reject()  # Reject on smoke failure; never accept a fallback silently.
    timer.timeout.connect(record_dialog)
    timer.start(100)
    report = {'mode': 'real Windows GUI buttons + real COM; synthetic selections prepared programmatically',
              'manual_visual_acceptance': 'PENDING', 'cases': [], 'dialogs': dialogs}
    try:
        applications = {}
        report['connections'] = {}
        for target, progid in (('word', 'Word.Application'), ('wps', 'KWPS.Application')):
            try:
                applications[target] = GetActiveObject(progid)
                report['connections'][target] = 'connected'
            except Exception as error:
                report['connections'][target] = str(error)
        targets = ('word', 'wps') if args.target == 'both' else (args.target,)
        for target in targets:
            if target not in applications:
                raise RuntimeError(f'{target} is not connected; open the application/document and retry. No Office application was launched.')
            office = applications[target]
            target_dir = out / target
            target_dir.mkdir()
            window.settings_page.writer_target.setCurrentIndex(window.settings_page.writer_target.findData(target))
            assert SettingsService(settings.path).load().writer_target == target
            for key, page, expected_images in (
                ('person', window.person_word_page, 4), ('project', window.project_search_page, 2),
                ('qualification', window.qualification_search_page, 2), ('award', window.award_search_page, 2),
                ('finance', window.finance_search_page, 2), ('autofill', window.person_autofill_page, 4)):
                result = {'target': target, 'entry': key}
                report['cases'].append(result)
                doc = None
                try:
                    doc = office.Documents.Add()
                    office.Visible = True
                    doc.Activate()
                    doc.Content.Text = 'BEFORE\rAFTER\r'
                    doc.Range(7, 7).Select()
                    normal = str(doc.Styles.Item(-1).NameLocal)
                    settings.save(replace(settings.load(), image_style=normal, person_name_style=normal))
                    window.settings_page.show_settings(settings.load())
                    if key == 'person':
                        page.job.insert_person_name = True
                        for i in range(1, 5):
                            page.job.add(i)
                            page.job.item(i).selected_certificate_ids = {i*100+1}
                    elif key == 'project':
                        page.job.insert_project_name = True
                        for i in (1, 2):
                            page.job.add(i)
                            page.job.item(i).selected_attachment_types = {'合成合同'}
                    elif key == 'autofill':
                        page.include_title.setChecked(True)
                        page.title_text.setText('合成自动填表标题')
                        page.include_note.setChecked(True)
                        page.note_text.setPlainText('合成注释\n第二行')
                        for i in range(1, 5):
                            page.task.add(i, f'测试人员{i}')
                            page.task.item(i).attachment_certificate_ids = {i*100+1}
                            page.task.item(i).role_text = f'合成职务{i}'
                        page.refresh()
                    else:
                        page.selected_ids.update((1, 2))
                        (page.insert_name if key == 'qualification' else page.insert_title).setChecked(True)
                    window.findChild(QStackedWidget, 'workspace').setCurrentWidget(page)
                    app.processEvents()
                    other = applications.get('wps' if target == 'word' else 'word')
                    before_other = [(int(other.Documents.Item(i).Content.End)) for i in range(1, other.Documents.Count+1)] if other is not None else None
                    dialog_count = len(dialogs)
                    page.output_button.click()  # Actual connected production GUI handler.
                    app.processEvents()
                    error = getattr(page, 'error_label', None)
                    result.update(images=int(doc.InlineShapes.Count), tables=int(doc.Tables.Count),
                                  text=doc.Content.Text, cursor=int(office.Selection.Start),
                                  gui_error=error.text() if error is not None else '',
                                  dialogs=dialogs[dialog_count:])
                    after_other = [(int(other.Documents.Item(i).Content.End)) for i in range(1, other.Documents.Count+1)] if other is not None else None
                    result['other_application_unchanged'] = before_other == after_other if other is not None else 'NOT AVAILABLE'
                    assert before_other == after_other, 'Non-target application changed'
                    assert not result['gui_error'] and not result['dialogs'], 'GUI reported insertion failure'
                    assert result['images'] == expected_images, 'Missing/duplicate images'
                    assert result['tables'] == (2 if key == 'autofill' else 0), 'Unexpected table count'
                    assert result['text'].startswith('BEFORE\r') and 'AFTER' in result['text'], 'Surrounding content lost'
                    result['status'] = 'PASS (structural smoke, not manual visual acceptance)'
                except Exception:
                    result['status'] = 'FAIL'
                    result['exception'] = traceback.format_exc()
                finally:
                    if doc is not None:
                        try:
                            doc.SaveAs2(str(target_dir / (key + '.docx')), 16)
                        except Exception:
                            result['save_error'] = traceback.format_exc()
        report['success'] = all(c.get('status', '').startswith('PASS') and not c.get('save_error') for c in report['cases'])
    except Exception:
        report['fatal'] = traceback.format_exc()
        report['success'] = False
    finally:
        timer.stop()
        window.close()
        app.processEvents()
        (out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(out / 'results.json')
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
