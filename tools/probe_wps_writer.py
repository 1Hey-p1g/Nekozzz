"""Independent COM probe. Default: read-only. Writing requires --write-tests.

Never writes an existing document, changes registry, quits Office or deletes
table-end markers. No production imports or third-party XML packages.
"""
import argparse
import base64
from datetime import datetime
import json
from pathlib import Path
import sys
import winreg
import zipfile

import pythoncom
import win32com.client

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
P = 'http://schemas.microsoft.com/office/2006/xmlPackage'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1cAAAAASUVORK5CYII='
TEXT = '<w:p><w:r><w:t>探测中文 TEXT 1</w:t></w:r></w:p>'
TABLE = ('<w:tbl><w:tblPr><w:tblW w:w="4000" w:type="dxa"/>'
         '<w:tblBorders><w:top w:val="single"/><w:bottom w:val="single"/>'
         '<w:left w:val="single"/><w:right w:val="single"/>'
         '<w:insideH w:val="single"/><w:insideV w:val="single"/></w:tblBorders></w:tblPr>'
         '<w:tblGrid><w:gridCol w:w="2000"/><w:gridCol w:w="2000"/></w:tblGrid>'
         + ''.join('<w:tr>' + ''.join('<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/>'
           '</w:tcPr><w:p><w:r><w:t>' + value + '</w:t></w:r></w:p></w:tc>'
           for value in row) + '</w:tr>' for row in (('A1 中文', 'B1'), ('A2', 'B2'))) + '</w:tbl><w:p/>')
FORMATTED = ('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr>'
             '<w:rFonts w:ascii="Calibri" w:eastAsia="宋体"/><w:b/><w:sz w:val="28"/>'
             '</w:rPr><w:t xml:space="preserve">  格式 中文  </w:t><w:tab/><w:t>TAB</w:t>'
             '<w:br/><w:t>第二行</w:t><w:br w:type="page"/></w:r></w:p>' + TABLE)
IMAGE = ('<w:p><w:r><w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
         '<wp:extent cx="914400" cy="914400"/><wp:docPr id="1" name="probe image"/>'
         '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
         '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
         '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
         '<pic:nvPicPr><pic:cNvPr id="1" name="probe.png"/><pic:cNvPicPr/></pic:nvPicPr>'
         '<pic:blipFill><a:blip xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:embed="rIdImage"/>'
         '<a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/>'
         '<a:ext cx="914400" cy="914400"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
         '</pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>')


def document_xml(body):
    return f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>'


def flat_xml(body, image=False):
    xml = (f'<pkg:package xmlns:pkg="{P}"><pkg:part pkg:name="/_rels/.rels" '
           f'pkg:contentType="application/vnd.openxmlformats-package.relationships+xml"><pkg:xmlData>'
           f'<Relationships xmlns="{REL}"><Relationship Id="rId1" '
           'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
           'Target="word/document.xml"/></Relationships></pkg:xmlData></pkg:part>'
           '<pkg:part pkg:name="/word/document.xml" pkg:contentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml">'
           f'<pkg:xmlData>{document_xml(body)}</pkg:xmlData></pkg:part>')
    if image:
        xml += (f'<pkg:part pkg:name="/word/_rels/document.xml.rels" pkg:contentType="application/vnd.openxmlformats-package.relationships+xml">'
                f'<pkg:xmlData><Relationships xmlns="{REL}"><Relationship Id="rIdImage" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/probe.png"/>'
                '</Relationships></pkg:xmlData></pkg:part><pkg:part pkg:name="/word/media/probe.png" pkg:contentType="image/png">'
                f'<pkg:binaryData>{PNG}</pkg:binaryData></pkg:part>')
    return xml + '</pkg:package>'


def registry():
    found = {}
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        names = {'kwps.application', 'wps.application', 'Word.Application'}
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, '', 0, winreg.KEY_READ | view) as root:
                for i in range(winreg.QueryInfoKey(root)[0]):
                    name = winreg.EnumKey(root, i)
                    if name.lower().startswith(('kwps.application', 'wps.application')):
                        names.add(name)
        except OSError:
            pass
        for name in sorted(names):
            result = {'progid': name, 'view': view}
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, name + '\\CLSID', 0, winreg.KEY_READ | view) as key:
                    clsid = winreg.QueryValueEx(key, None)[0]
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, 'CLSID\\' + clsid + '\\LocalServer32', 0, winreg.KEY_READ | view) as key:
                    server = winreg.QueryValueEx(key, None)[0]
                result.update(clsid=clsid, server=server)
            except OSError as error:
                result['error'] = str(error)
            found[f'{name}:{view}'] = result
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--progid', default='kwps.application')
    parser.add_argument('--dispatch', action='store_true', help='Explicitly permit Dispatch, which can launch the selected program.')
    parser.add_argument('--write-tests', action='store_true', help='Create new test documents only; existing documents are never written.')
    parser.add_argument('--production-primitives', action='store_true', help='Also exercise unchanged WordService/WordTableCursor on a new test document.')
    parser.add_argument('--output', type=Path, default=Path.home() / 'Desktop/Nekozzz_WPS_Probe')
    args = parser.parse_args()
    out = args.output.resolve() / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    out.mkdir(parents=True, exist_ok=False)
    report = {'python': sys.version, 'registry': registry(), 'calls': [], 'manual_visual_result': 'PENDING'}

    def call(name, operation, describe=lambda value: value if isinstance(value, (dict, list, str, int, float, bool, type(None))) else str(value)):
        item = {'name': name}
        try:
            value = operation()
            item.update(status='CALL SUCCEEDED (not visual acceptance)', result=describe(value))
            return value
        except Exception as error:
            cause = error
            while getattr(cause, '__cause__', None) is not None:
                cause = cause.__cause__
            hr = getattr(cause, 'hresult', None)
            item.update(status='FAILED', exception=type(error).__name__, message=str(error),
                        hresult=hr, hresult_hex=f'0x{hr & 0xffffffff:08X}' if hr is not None else None,
                        excepinfo=getattr(error, 'excepinfo', None))
            item['underlying_message'] = str(cause)
        finally:
            report['calls'].append(item)

    pythoncom.CoInitialize()
    try:
        names = {'kwps.application', 'wps.application', 'Word.Application', args.progid}
        names.update(v['progid'] for v in report['registry'].values() if 'clsid' in v)
        apps = {}
        for name in sorted(names):
            app = call('GetActiveObject ' + name, lambda name=name: win32com.client.GetActiveObject(name), lambda _: 'connected')
            if app is not None:
                apps[name] = app
                call(name + ' Documents.Count', lambda: int(app.Documents.Count))
                call(name + ' Application.Version', lambda: app.Version)
                call(name + ' ActiveDocument', lambda: app.ActiveDocument, lambda _: 'available (no document content recorded)')
                call(name + ' Selection', lambda: app.Selection, lambda _: 'available')
                call(name + ' Selection.Range', lambda: app.Selection.Range, lambda r: {'start': r.Start, 'end': r.End})
        app = apps.get(args.progid)
        if args.dispatch:
            app = call('Dispatch ' + args.progid, lambda: win32com.client.Dispatch(args.progid), lambda _: 'connected')
        else:
            report['calls'].append({'name': 'Dispatch', 'status': 'NOT ATTEMPTED; use --dispatch explicitly'})
        if args.write_tests and app is not None:
            # No existing ActiveDocument becomes a write target. Only Add() results.
            cases = [('01_text', TEXT, False), ('02_table', TABLE, False),
                     ('03_format', FORMATTED, False), ('04_image_relation', IMAGE, True),
                     ('05_body_middle', TABLE, False), ('06_inside_cell', TABLE, False)]
            for name, body, image in cases:
                def run_case():
                    doc = app.Documents.Add()
                    app.Visible = True
                    doc.Activate()
                    position = 0
                    if name == '05_body_middle':
                        doc.Content.Text = 'BEFORE\rAFTER\r'
                        position = 7
                    if name == '06_inside_cell':
                        outer = doc.Tables.Add(doc.Range(0, 0), 1, 1)
                        position = outer.Cell(1, 1).Range.Start
                    insertion = doc.Range(position, position)
                    insertion.Select()
                    xml = flat_xml(body, image)
                    (out / (name + '.xml')).write_text(xml, encoding='utf-8')
                    before = int(doc.Content.End)
                    call(name + ' Range.InsertXML', lambda: insertion.InsertXML(xml))
                    result = call(name + ' post-state', lambda: {
                        'content_end_before': before, 'content_end_after': int(doc.Content.End),
                        'tables': int(doc.Tables.Count), 'paragraphs': int(doc.Paragraphs.Count),
                        'inline_images': int(doc.InlineShapes.Count), 'text': doc.Content.Text,
                        'selection_start': int(app.Selection.Start), 'selection_end': int(app.Selection.End)})
                    target = out / (name + '.docx')
                    call(name + ' SaveAs2', lambda: doc.SaveAs2(str(target), 16))
                    return result
                call(name + ' test document', run_case, lambda _: 'see post-state and saved document')
            # A retained DOCX fixture tests InsertFile separately; not a production fallback.
            source = out / 'insertfile_source.docx'
            with zipfile.ZipFile(source, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                    '<Default Extension="xml" ContentType="application/xml"/>'
                    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
                archive.writestr('_rels/.rels', f'<Relationships xmlns="{REL}"><Relationship Id="rId1" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
                archive.writestr('word/document.xml', document_xml(FORMATTED))
            def insert_file():
                doc = app.Documents.Add()
                doc.Activate()
                doc.Range(0, 0).Select()
                call('07 Selection.Range.InsertFile', lambda: app.Selection.Range.InsertFile(str(source)))
                call('07 SaveAs2', lambda: doc.SaveAs2(str(out / '07_insertfile.docx'), 16))
            call('07 test document', insert_file)
            if args.production_primitives:
                def primitives():
                    root = Path(__file__).resolve().parents[1]
                    sys.path.insert(0, str(root))
                    from services.word_service import WordService
                    from services.autofill.word_cursor import WordTableCursor
                    from services.autofill import template_core, table_xml
                    template = root / 'resources/templates/personnel_table.docx'
                    _, _, _, table = template_core.load_template(template)
                    for index, block in enumerate(template_core.BLOCKS, 1):
                        for field, address in block.targets().items():
                            template_core.replace_target_text_preserving_format(
                                template_core.cell_at(table, address), f'人员{index} {field} 中文长文字 空格\n换行\t制表')
                    with zipfile.ZipFile(template) as archive:
                        table_xml.freeze_inherited_format(table, archive.read('word/styles.xml'))
                    table_xml.fit_table_to_available_width(table, 400)
                    xml = table_xml.flat_package([table, table_xml.ending_paragraph()])
                    (out / '08_production_primitives.xml').write_text(xml, encoding='utf-8')
                    doc = app.Documents.Add()
                    doc.Activate()
                    doc.Content.Text = 'BEFORE\rAFTER\r'
                    doc.Range(7, 7).Select()
                    image = out / 'probe.png'
                    image.write_bytes(base64.b64decode(PNG))
                    try:
                        word = WordService(app)
                        cursor = WordTableCursor(word)
                        cursor.assert_unchanged()
                        cursor.boundary()
                        cursor.text('自动填表探测标题', None, True)
                        cursor.table(xml)
                        cursor.text('注释\n换行', None, True)
                        for index in (1, 2, 3):
                            cursor.boundary()
                            cursor.text(f'人员{index}', None, True)
                            cursor.image_style(None, True)
                            cursor.insert_inline_image(image, shrink_oversized=True, enlarge_small=False)
                        cursor.page_break()
                        cursor.finish()
                        return {'tables': int(doc.Tables.Count), 'images': int(doc.InlineShapes.Count),
                                'selection_start': int(app.Selection.Start), 'cursor_position': cursor.position}
                    finally:
                        call('08 SaveAs2 (possibly partial; inspect result)', lambda: doc.SaveAs2(str(out / '08_production_primitives.docx'), 16))
                call('08 unchanged production primitives', primitives)
        elif args.write_tests:
            report['write_tests'] = 'NOT AVAILABLE: selected application connection failed'
        else:
            report['write_tests'] = 'NOT ATTEMPTED: read-only probe'
    finally:
        pythoncom.CoUninitialize()
        (out / 'probe_results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        print(out / 'probe_results.json')


if __name__ == '__main__':
    main()
