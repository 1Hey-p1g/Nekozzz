# Third-party notices — FINAL Nekozzz 0.9.2 accepted runtime

Copyright © 2026 1Hey-p1g. Nekozzz is **AGPL-3.0-only**; root LICENSE is its full text.
This table describes the accepted RC, not historical inventories. It does not
relicense upstream code. See SOURCE_AVAILABILITY.md and the final release clearance
report for source-delivery preparation and the manual publication steps.

## Distributed runtime

| Component | Version | License family | Original full notice location | Upstream / source |
|---|---|---|---|---|
| CPython runtime and stdlib | 3.14.7 | PSF and historical licenses, embedded dependency notices | licenses/CPython/LICENSE.txt | https://www.python.org/downloads/ ; Python-3.14.7.tar.xz |
| PySide6 / Shiboken6 | 6.11.2 | LGPL-3.0 / GPL alternatives, upstream individual files retain terms | licenses/PySide6*, licenses/shiboken6, licenses/upstream_sources/pyside-setup-everywhere-src-6.11.2 | https://doc.qt.io/qtforpython-6/ ; pyside-setup source |
| Qt Core/Gui/Widgets/UiTools/OpenGLWidgets/OpenGL/Svg | 6.11.2 | LGPL-3.0 option for these libraries; embedded code has separate licenses | licenses/upstream_sources/qtbase*, qttools*, qtsvg*; licenses/GNU | https://doc.qt.io/qt-6/licensing.html ; exact source archives |
| PyMuPDF / MuPDF | 1.28.2 / 1.28.2 | AGPLv3 open-source option; commercial option not selected | licenses/PyMuPDF and licenses/upstream_sources/pymupdf*, mupdf* | https://github.com/pymupdf/PyMuPDF ; https://mupdf.com/ |
| openpyxl | 3.1.5 | MIT | licenses/openpyxl | https://openpyxl.readthedocs.io/ |
| et_xmlfile | 2.0.0 | MIT | licenses/et_xmlfile | https://pypi.org/project/et-xmlfile/ |
| pyodbc | 5.3.0 | MIT-0 | licenses/pyodbc | https://github.com/mkleehammer/pyodbc |
| pywin32 | 312 | Original PythonWin/PSF/permissive component terms | licenses/pywin32 | https://github.com/mhammond/pywin32 |
| OpenSSL | 3.5.7 | Apache-2.0 | licenses/native/OpenSSL; exact upstream notices | https://openssl.org/ ; openssl-3.5.7.tar.gz |
| libffi | CPython recipe 3.4.4 (DLL ABI 8 is not a version) | MIT | CPython LICENSE embedded notices | CPython PCbuild recipe; https://github.com/libffi/libffi |
| SQLite | 3.50.4 | Public domain | CPython notices; no conventional license grant needed | https://sqlite.org/copyright.html |
| CPython embedded compression/XML/decimal code | see interpreter license and PCbuild recipe | zlib-ng/zlib, Expat, bzip2, xz, Zstandard, libmpdec and other original terms | CPython full LICENSE | exact CPython source contains recipe and notices |
| PyInstaller embedded bootloader/importer/bootstrap | 6.22.3 | GPL-2.0-or-later with bootloader exception | licenses/PyInstaller | https://pyinstaller.org/ |
| Embedded runtime hooks | hooks-contrib 2026.8 / PyInstaller 6.22.3 | actual runtime hook Apache-2.0 headers | licenses/pyinstaller-hooks-contrib and PyInstaller | build tooling notices apply to embedded runtime portion |

Original files retain full required copyright, permission and disclaimer wording.
Copyright owners are the upstream authors named in those files, not Nekozzz's
developer. Package directory wildcard notation above refers to directories, not
new license grants. See licenses/release_manifest.json for exact files and hashes.

## Qt plugin / embedded attribution boundary

Retained: qwindows, qmodernwindowsstyle, qjpeg, qico, qsvg, qsvgicon.
PNG is built into QtGui. Supported image policy is PNG/JPEG/ICO/SVG; GIF, ICNS,
TGA, TIFF, WBMP and WebP are not guaranteed. JPEG/PNG, font/text shaping and
compression notices from qtbase, and SVG notices from qtsvg are preserved.
The source archives contain original qt_attribution.json, REUSE and license
files, including libjpeg-turbo, libpng, zlib, FreeType, HarfBuzz and others.
These are conservative source-tree notices, not a claim every upstream file
was compiled. Removed QtImageFormats codecs are not listed as final runtime.

Qt libraries/bindings/plugins remain independent dynamic files in _internal.
Compatible architecture/ABI Qt/PySide/Shiboken libraries can be replaced there;
preserve the dependent library set. No binary signing/installation lock is added.
Nekozzz imposes no restriction on reverse engineering for debugging library
modifications. See LGPL_REPLACEMENT.md for paths and source delivery method.

## MuPDF incorporated third-party code

The unchanged native trio is pymupdf/_extra.pyd, _mupdf.pyd, mupdfcpp64.dll.
Full MuPDF thirdparty and resource source/notices are supplied conservatively,
including font notices. Code availability is not limited by the APIs Nekozzz
uses: not calling OCR/barcodes does not establish their absence from the DLL.
The retained full-source notice tree includes compression, font/rendering,
parsing, image, OCR and barcode components; compilation distinctions and
generation/configuration instructions are recorded in the source map and
CORRESPONDING_SOURCE_BUILD_GUIDE.md.
Preserve these original notices when delivering corresponding source.

## Outside final runtime

**Not included:** lxml and its former seven native extensions; software OpenGL
opengl32sw/Mesa/LLVM payload; QtNetwork/TLS/networkinformation deployment;
VirtualKeyboard/QML/Quick; Qt PDF/qpdf; removed optional image plugins; Microsoft
VC runtime private copies. Historical lxml and removed-component evidence is
retained locally and is not a final runtime dependency table.

Pillow 12.3.0, PyInstaller build machinery, hooks-contrib build hooks, altgraph,
packaging, pefile, setuptools and pywin32-ctypes are build/audit dependencies;
their installed notices remain in the source repository where relevant.
Only the embedded PyInstaller/runtime-hook portions are distributed runtime.
python-docx and historical lxml baselines are experimental/audit only.

## External prerequisites (not redistributed)

Microsoft Visual C++ v14 **x64** Runtime must be sufficiently recent on Windows
10/11. Install from Microsoft's official documentation if missing:
https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist
Nekozzz supplies neither VC DLLs nor vc_redist installer. Desktop Microsoft Word
is required for Word integration; a compatible 64-bit Access ODBC driver is
required only for Access migration. No Microsoft redistribution entitlement
is claimed for these external products.

## Source delivery

Provide same-release Nekozzz source and required library source/build materials
alongside the binary with stable immutable artifact names and hashes. A moving
latest GitHub branch or homepage is not this binary's corresponding source.
See SOURCE_AVAILABILITY.md, SOURCE_DELIVERY_INDEX.json and FINAL_RELEASE_SOURCE_MAP.md.
Local preparation is not completed public conveyance; no URL is fabricated.
