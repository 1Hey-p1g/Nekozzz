# Nekozzz 0.9.3 RC source map

Authority: built 0.9.3 RC executable SHA256
`84c2240bff1b8e5003989592e1df4524cadf13c579d2bc98c41066654a868823`.

Application: current source view source/; versions 0.9.3 / schema 1 / backup 1;
validated stdlib adapter, no lxml. Exact manifest accompanies that view.

Qt Core/Gui/Widgets/OpenGL/OpenGLWidgets and qwindows/style/jpeg/ico come from
qtbase 6.11.2; UiTools from qttools; Svg/qsvg/qsvgicon from qtsvg. Bindings and
Shiboken come from pyside-setup 6.11.2. QtUiTools hard closure is retained.
No QtNetwork or QtImageFormats optional plugin binaries are distributed.
Original module/embedded-code terms are preserved; archives may include tools
with different terms which are not claims of runtime inclusion.

PyMuPDF native trio is byte-identical to the official 1.28.2 Windows wheel:
_extra.pyd 43292c50f18dafa1d92dec67e076d2340a361a24e510edb6ccfe8de7364b6b10;
_mupdf.pyd 8b0a0a990523eaecf695ec7f9bb5660047b11948649a7e89369141c03dc589d9;
mupdfcpp64.dll 998184dce298f24a4c2b080a9173594c96c6f78796732bdd8e95ca0e557557cb.
Official wheel SHA ebd244918798502d7b4504c90410d1711a4d7675a32584ca30f1bab419ecbffe.
Its _build.py records PyMuPDF commit 12786d12b2962a1d77fd13b103162eddf749644c,
empty PyMuPDF working diff, MuPDF exact archive URL, SWIG 4.4.1, fake_no_gil=False.
Both sdist and full exact commit archive are delivered, plus full MuPDF source
including thirdparty/resources and generation/build scripts. Six generated
headers are reference inputs, not a claim all generated implementation is saved.
setup.py + scripts/gh_release.py and MuPDF scripts/mupdfwrap.py are upstream
entrypoints; use their Windows x64 shared release target and documented variables.
Automatic regeneration and the relevant configuration are documented in CORRESPONDING_SOURCE_BUILD_GUIDE.md; exact original release environment capture is not a missing source gate.
Nekozzz has not changed these natives; lack of OCR API use does not remove
OCR/barcode/font source/notices from the conservatively supplied source set.

CPython full source/PCbuild and OpenSSL exact source accompany original runtime
notices; permissive/public-domain components do not acquire AGPL merely by use.
CPython LICENSE contains interpreter embedded library notices. PyInstaller
bootloader exception applies to its runtime, not other components.

All archive names/hashes/official URLs: SOURCE_DELIVERY_INDEX.json. Native byte
identity and mappings: report/release_0.9.3/ (fresh RC verification) and report/final_release_clearance/ (hash-matched upstream evidence). The practical source/generation/replacement set is complete locally. Public source
conveyance awaits manual publication and recipient-access verification.
