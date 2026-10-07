# LGPL replacement and source delivery — Nekozzz 0.9.2

Qt 6.11.2 Core/Gui/Widgets/UiTools/OpenGLWidgets/OpenGL/Svg are separate DLLs
under _internal/PySide6. Binding .pyd files and pyside6.abi3.dll are there too;
Shiboken.pyd/shiboken6.abi3.dll are in _internal/shiboken6. Plugins are below
_internal/PySide6/plugins. They are dynamically imported, not static-linked
into the application EXE. See final inventory for exact paths/imports.

Keep a backup, stop Nekozzz, then replace the desired libraries with compatible
x64 ABI/interface versions and all dependencies. Preserve qwindows and the
retained style/image/SVG plugins. Changes must preserve required interfaces;
arbitrary incompatible Qt versions are not promised to work. No integrity lock
prevents this. No actual rebuilt-library swap test is claimed.

Nekozzz permits reverse engineering for debugging modifications to LGPL
components. It imposes no additional restriction or proprietary EULA. Full
LGPLv3 and referenced GPLv3 texts and original attribution are supplied.

The chosen release method is equivalent recipient download access to exact
corresponding library source alongside the binary (not a bare homepage and
not an unfulfilled written offer). Exact sources are staged under
corresponding-source; CORRESPONDING_SOURCE_BUILD_GUIDE.md documents complete
source/generator inputs and compatible-library build/replacement instructions.
Only actual manual publication and recipient source access remain to perform.
For these independent shared libraries the intended LGPLv3 section 4(d)(1)
mechanism is compatible-library replacement; separate static application
object files are not required by that chosen mechanism. No installation
information beyond portable file replacement is currently imposed by Nekozzz.
