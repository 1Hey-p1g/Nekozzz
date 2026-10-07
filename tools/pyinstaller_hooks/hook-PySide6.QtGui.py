"""Keep the upstream QtGui collector; omit only verified unused plugins.

Filter before recursive binary dependency analysis, so a removed plugin cannot
leave its Qt DLL dependency chain in the application bundle.
"""
from pathlib import Path
from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
OMITTED_PLUGINS = {
    'qtvirtualkeyboardplugin.dll', 'qpdf.dll', 'qtuiotouchplugin.dll',
    'qdirect2d.dll', 'qminimal.dll', 'qoffscreen.dll',
    'qgif.dll', 'qicns.dll', 'qtga.dll', 'qtiff.dll', 'qwbmp.dll', 'qwebp.dll',
    'opengl32sw.dll',
}
binaries = [(src, dst) for src, dst in binaries if Path(src).name.lower() not in OMITTED_PLUGINS]
