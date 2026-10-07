# Nekozzz 0.9.2 — Corresponding Source build / generation companion

## Scope and conclusion

This guide accompanies the exact immutable archives in SOURCE_DELIVERY_INDEX.json.
It closes the two delivery questions; it does not rebuild/change the accepted RC.
Commands below are recipient recipes with example paths, **not executed here**.
No assertion of bit-identical wheel reconstruction or a tested library swap.

AGPLv3 section 1 requires the source and controlling scripts for generation,
installation, running and modification; automatically regenerable outputs need
not be duplicated. LGPLv3 shared-library replacement is documented separately.
Generally available unmodified tools/System Libraries are not missing covered
source. Native modification/ABI compatibility matters; timestamps/hostname and
an identical proprietary compiler/SDK patch level alone do not.

## 1. Qt / PySide6 / Shiboken6 6.11.2

### Source and modification evidence

Supply qtbase, qttools, qtsvg and pyside-setup exact 6.11.2 archives, intact.
qtbase supplies Core/Gui/Widgets/OpenGL/OpenGLWidgets, qwindows, Windows style,
JPEG/ICO support; qttools supplies UiTools; qtsvg supplies Svg/qsvg/qsvgicon.
The pyside-setup archive includes Shiboken runtime AND its generator sources,
PySide support, typesystems, glue, module CMake files and build/package scripts.
All handwritten inputs and Qt interface headers can thus be modified/regenerated.

22 retained DLL/PYD/plugin files match installed upstream payload and its RECORD.
No Nekozzz downstream source/native patch exists; packaging selected unchanged
upstream files. A source patch is not invented from the difference between the
full upstream wheel and the distributed subset. This is not a claim that every
historical upstream compiler option has been recovered.

131 installed typesystem/glue input files match the exact source after ONLY the
documented CMake installation transformation and newline convention. Specifically,
sources/pyside6/cmake/Macros/PySideModules.cmake strips the module directory from
load-typesystem paths for the installed flat typesystems directory (lines 384–395
in this archive). The transformation is already supplied as source, not an
unavailable proprietary patch. The same macro supplies the Shiboken command,
Qt API version, header/include paths, typesystem paths, output and license file.
These are binding-generator inputs, not merely version strings.

### Build prerequisites and procedure (independent recipient directory)

Use an x64 MSVC Qt-supported build environment, CMake/Ninja, Python and the
libclang/LLVM development tools required by this exact source. Consult the
archive's CMake checks and README/README.pyside6/README.shiboken6 for supported
versions. No tools are installed or downloaded by Nekozzz/the closure task.
Do not build inside the accepted portable application directory.

Extract the four archives with their original directories. In an x64 developer
shell, choose an empty install prefix and separate build directories, e.g.:

```powershell
$qtPrefix = 'C:
ecipient-buildqt-6.11.2'
cmake -S .qtbase-everywhere-src-6.11.2 -B .uild-qtbase -G Ninja `
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=$qtPrefix `
  -DBUILD_SHARED_LIBS=ON -DQT_BUILD_TESTS=OFF -DQT_BUILD_EXAMPLES=OFF
cmake --build .uild-qtbase
cmake --install .uild-qtbase
cmake -S .qttools-everywhere-src-6.11.2 -B .uild-qttools -G Ninja `
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=$qtPrefix `
  -DCMAKE_INSTALL_PREFIX=$qtPrefix -DQT_BUILD_TESTS=OFF -DQT_BUILD_EXAMPLES=OFF
cmake --build .uild-qttools
cmake --install .uild-qttools
cmake -S .qtsvg-everywhere-src-6.11.2 -B .uild-qtsvg -G Ninja `
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=$qtPrefix `
  -DCMAKE_INSTALL_PREFIX=$qtPrefix -DQT_BUILD_TESTS=OFF -DQT_BUILD_EXAMPLES=OFF
cmake --build .uild-qtsvg
cmake --install .uild-qtsvg
```

Keep the normal desktop Gui/Widgets/OpenGL/OpenGLWidgets feature interfaces,
Windows platform/native style and JPEG/ICO/PNG support enabled; do not disable
them to shrink a recipient build. Configure summaries/generated feature headers
are generated from supplied CMake/configure source and available dependencies.
They are not separately missing handwritten source. Source supplies embedded
codec/text/font implementation and feature alternatives, even if default local
feature detection differs. For explicit feature selection use qtbase configure
and its documented options, then inspect its summary. These commands define a
compatible modification build, NOT an assertion of the upstream wheel's exact
original CMake command. Building incidental module/tool intermediates is allowed;
this does not add them to the frozen Nekozzz release boundary.

In a separate Python build environment with upstream requirements available:

```powershell
Set-Location .pyside-setup-everywhere-src-6.11.2
python setup.py build --build-type=all --ignore-git --limited-api=yes `
  --module-subset=Core,Gui,Widgets,UiTools,OpenGL,OpenGLWidgets `
  --qtpaths="$qtPrefixinqtpaths6.exe"
```

Build-type=all builds Shiboken runtime, generator and PySide bindings. With
--ignore-git the supplied release tree remains the selected source. Source
setup.py dispatches to build_scripts; sources/pyside6/.../PySideModules.cmake
invokes the generator on module headers/typesystems/glue. The command regenerates
wrapper C++/module headers then compiles them; wheel-only generated C++ recovery
is not necessary. Limited API preserves the distributed ABI3 approach. Upstream
coin/instructions_utils.py independently documents setup.py build, standalone,
limited-api=yes and the Qt path. Packaging/qt.conf handling is in the supplied
Windows deployment scripts/README, including automatically embedded relative
Qt prefix. LLVM/compiler dependency checks are in the full archive.

If installing into this recipient's environment, use upstream setup.py install
or bdist_wheel with the same settings; this is NOT an instruction to reinstall
Nekozzz production dependencies. Validate compatible exported interfaces and
required DLL imports before replacing library files in a disposable portable
copy. LGPL_REPLACEMENT.md gives exact destination paths and required closure.
Keep matching pyside6.abi3.dll/shiboken6.abi3.dll, required .pyd modules and plugin
dependencies coherent. QtSvg.pyd is not required by Nekozzz; do not introduce it
into the accepted runtime. No particular same-file hash is an acceptance target.

### Closure assessment

Exact covered source, generator definitions, installation transformation and
public build/control scripts plus this compatible-build/replacement procedure
are sufficient for the recipient modification route. No concrete unavailable
source change or proprietary generator input has been identified. Previously
unknown entire-wheel configure logs are provenance limits, not evidence of a
required missing source file. No affirmative guarantee of arbitrary incompatible
replacement builds is made. No Nekozzz patch set needs to be supplied.

Official supporting instructions:
https://doc.qt.io/qt-6.11/build-sources.html
https://doc.qt.io/qt-6.11/windows-building.html
The exact archives' build scripts/README are the version-pinned authority.

## 2. PyMuPDF / MuPDF 1.28.2

### Source identity and no downstream patch

Supply exact PyMuPDF sdist plus full archive of recorded commit
12786d12b2962a1d77fd13b103162eddf749644c (CI/scripts supplement), and full
mupdf-1.28.2-source.tar.gz with all thirdparty/resources. The distributed native
trio matches the official wheel. Its _build.py names that commit, an empty
PyMuPDF working diff, the exact MuPDF archive URL, SWIG 4.4.1 and fake_no_gil=False.
Nekozzz did not modify these upstream binaries/sources. Known Windows default
config adjustment for MuPDF >=1.28 is an existing ReleaseTofuCjkExt build target,
not the older config.h rewrite. Any standard project-upgrade generation logic
is in the supplied scripts; no separate Nekozzz patch is omitted.

### Generation/tool dependencies

Use **SWIG 4.4.1** on PATH and for PYMUPDF_SETUP_SWIG. Use the usual libclang
Python bindings/native library for the source C-header parser, pipcl (backend,
including its wdev/extension helpers), Python x64, and the upstream Windows
devenv-capable MSVC environment with the project toolset supported by the source
(the original projects use v142; the source supports VS project upgrade).
The source's get_requires_for_build_wheel declares pipcl/libclang/SWIG needs;
libclang is not pinned to one Windows version there. These unmodified general
build tools do not become missing covered source. Their exact temporary paths
or build machine need not be recovered. Do not use URL_WHEEL/DUMMY/rebuild=0 to
masquerade a downloaded wheel as a source build.

Extract the MuPDF archive into an independent directory. Build from the
PyMuPDF sdist or exact Git archive with identical source layout and local MuPDF:

```powershell
# In a recipient-owned build environment with dependencies already available:
Set-Location .pymupdf-1.28.2
$env:PYMUPDF_SETUP_MUPDF_BUILD = (Resolve-Path '..mupdf-1.28.2-source').Path
$env:PYMUPDF_SETUP_MUPDF_BUILD_TYPE = 'release'
$env:PYMUPDF_SETUP_MUPDF_TESSERACT = '1'
$env:PYMUPDF_SETUP_MUPDF_OVERWRITE_CONFIG = '1'
$env:PYMUPDF_SETUP_PY_LIMITED_API = '1'
$env:PYMUPDF_SETUP_MUPDF_REBUILD = '1'
$env:PYMUPDF_SETUP_SWIG = (Get-Command swig).Source  # verify SWIG 4.4.1
# Set PYMUPDF_SETUP_DEVENV only if automatic discovery cannot find devenv.com.
# Keep SWIG 4.4.1 on PATH too: the MuPDF wrapper and extra extension both use it.
Remove-Item Env:PYMUPDF_SETUP_URL_WHEEL,Env:PYMUPDF_SETUP_DUMMY,`
  Env:PYMUPDF_SETUP_FAKE_NOGIL,Env:PYMUPDF_SETUP_MUPDF_REFCHECK_IF,`
  Env:PYMUPDF_SETUP_MUPDF_TRACE_IF -ErrorAction SilentlyContinue
python -m pip wheel --no-build-isolation --no-deps . --wheel-dir .
ecipient-wheel
```

This is a documented generation configuration preserving full source and OCR;
it is not asserted to be a captured original release environment. BuildType=release
is the source default; TESSERACT=1 includes evidenced OCR instead of discarding
it; OVERWRITE_CONFIG=1 chooses the >=1.28 TOFU_CJK_EXT target; limited API is
the evidenced ABI3 mode, fake_no_gil off is recorded. Reference-count/trace knobs
are optional diagnostic variants whose generating code is supplied. They do not
select inaccessible source. v142 project tools or the documented VS-upgrade path
must be available to the recipient; exact SDK patch/tool executable paths are
not covered source. User-selected general tool versions may yield different
bytes; that alone is not source incompleteness.

The backend setup.py calls MuPDF scripts/mupdfwrap.py with a shared-tesseract-
release-TOFU_CJK_EXT-Py_LIMITED_API_...-x64-py... build directory and `-b all`.
The supplied scripts/wrap/__main__.py expands Windows all into **0123**:

0. Parse MuPDF C headers through libclang; generate C++ wrapper source/headers.
1. Build the solution mupdfcpp target (and libmuthreads): linked MuPDF C plus
   thirdparty/resource code is in mupdfcpp64.dll, not a separate mupdf.dll.
2. Generate the Python binding/SWIG material from wrapper/interface definitions.
3. Compile/link the generated Python extension _mupdf.pyd.

PyMuPDF setup._build_extension independently calls pipcl.build_extension with
src/extra.i, source include dependencies and mupdfcpp64.lib to regenerate and
compile _extra.pyd. Generation settings, interfaces, output rules and license
comments are supplied in the archives. Available generated headers are useful
references, not a required substitute for handwritten interface/generator source.
All actual thirdparty/resource sources/notices are conservatively included; not
calling OCR/barcodes does not remove their materials. No OCR/barcode pruning.

After a recipient build, verify PyMuPDF/MuPDF version 1.28.2, x64/ABI3, native
trio/imports and intended feature behavior. A version/behavior difference may
require adjusting supported configuration but is not grounds to replace the
frozen release or require whole-file SHA equality. No reproduction was executed
and no new claim of tested generated output identity is made by this document.

### Closure assessment

Exact recorded revision/archive, full MuPDF source/thirdparty/resources,
SWIG interfaces, header-to-C++ generation source, controlling build scripts and
the explicit regeneration instructions form a practical Corresponding Source
delivery. No specific unavailable handwritten source/modification input remains.
The earlier missing generated C++/exact original environment concerns were
overbroad as delivery gates: automatically regenerable files are excluded by
AGPLv3 section 1, and supplied optional configurations do not by themselves imply
an omitted source dependency. Do not call the recipes bit-identical reproduction.

Official sources and archive SHA256 are in SOURCE_DELIVERY_INDEX.json.

## 3. Recipient delivery / independent replacement

Publish the unchanged same-version source archives, this guide, notices,
application source manifest and LGPL_REPLACEMENT.md with equivalent download
access alongside the binary. Do not rely only on moving upstream homepages.
There is no DRM/signing lock in Nekozzz; a compatible modified LGPL library can
replace the independent DLL/binding/plugin files. No additional reverse-
engineering restriction is imposed. Source delivery is the selected network
conveyance method, not a future unfulfilled written offer.

## 4. Accepted resource metadata

Developer chose A: existing Office creator/lastModifiedBy and local-directory
metadata may be disclosed. Frozen DOCX/Excel bytes and template signature are
unchanged. No other source/runtime/license investigation is reopened.
