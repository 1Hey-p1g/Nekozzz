# Windows onedir; only immutable application resources are included.
import sys
from pathlib import Path
root = Path(SPECPATH)
sys.path.insert(0, str(root))
from version import APP_NAME, APP_VERSION
from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct
numbers = tuple(int(part) for part in APP_VERSION.split('.')) + (0,)
metadata = VSVersionInfo(ffi=FixedFileInfo(filevers=numbers, prodvers=numbers,
    mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0,0)),
    kids=[StringFileInfo([StringTable('040904B0', [StringStruct(k,v) for k,v in
        [('ProductName',APP_NAME),('FileDescription',APP_NAME),('ProductVersion',APP_VERSION),
         ('FileVersion',APP_VERSION+'.0'),('LegalCopyright','Copyright © 2026 1Hey-p1g'),('InternalName',APP_NAME),('OriginalFilename',APP_NAME+'.exe')]])]),
        VarFileInfo([VarStruct('Translation',[1033,1200])])])
a = Analysis([str(root/'main.py')], pathex=[str(root)], binaries=[],
    datas=[(str(root/'ui/main_window.ui'),'ui'),
           (str(root/'LICENSE'),'.'),
           (str(root/'THIRD_PARTY_NOTICES.md'),'.'),
           (str(root/'SOURCE_AVAILABILITY.md'),'.'),
           (str(root/'licenses'),'licenses'),
           (str(root/'resources/icon.png'),'resources'),
           (str(root/'resources/templates/personnel_table.docx'),'resources/templates'),
           (str(root/'access source/DatabaseStructure.xlsx'),'access source')],
    hiddenimports=['win32com.client','pythoncom','pywintypes'], hookspath=[str(root/'tools/pyinstaller_hooks')],
    runtime_hooks=[], excludes=['pytest', 'PIL', 'lxml', 'PySide6.QtNetwork'], noarchive=False)
# Accepted runtime boundary: raster QWidget/QUiLoader, PNG/JPEG/ICO/SVG.
# Remove only the previously validated optional Qt set. VC v14 x64 is an
# external Microsoft prerequisite, never copied into this distribution.
omitted_runtime_files = {
    'opengl32sw.dll', 'qtuiotouchplugin.dll',
    'qdirect2d.dll', 'qminimal.dll', 'qoffscreen.dll', 'qt6network.dll',
    'qnetworklistmanager.dll', 'qcertonlybackend.dll', 'qopensslbackend.dll', 'qschannelbackend.dll',
    'qgif.dll', 'qicns.dll', 'qtga.dll', 'qtiff.dll', 'qwbmp.dll', 'qwebp.dll',
    'msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll', 'vcruntime140.dll', 'vcruntime140_1.dll',
}
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() not in omitted_runtime_files]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=APP_NAME,
    debug=False, strip=False, upx=False, console=False,
    icon=str(root/'resources/icon.ico'), version=metadata, contents_directory='_internal')
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=APP_NAME)
