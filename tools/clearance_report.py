"""Write the current clearance decision from local evidence; preserve historical reports."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def main():
    component_map = read('report/NEKOZZZ_BINARY_COMPONENT_MAP.json')
    counts = component_map['counts']
    tests = read('report/pruning/clearance_final_tests.json')
    verified = read('report/clearance/final_payload_verification.json')
    privacy = read('report/clearance/privacy_scan.json')
    artifacts = read('report/clearance/source_artifacts.json')
    manifest = read('licenses/manifest.json')
    source = read('report/clearance_sources/Nekozzz-0.9.2-source-candidate.manifest.json')
    text = '''# Nekozzz 0.9.2 — Final License Clearance

Date: 2026-10-03. Scope: current `dist/Nekozzz/` only. No further pruning.

## 1. Final Status

**NOT READY — LICENSE BLOCKERS REMAIN** (C).

Exact upstream sources and original notices have now been prepared locally,
but source/build correspondence, software OpenGL composite attribution and
Microsoft redistribution entitlement are not fully established. This is not
a READY decision. Missing second-PC QA alone is not treated as a license blocker.

## 2. Binary Identity

Nekozzz 0.9.2; AGPL-3.0-only; Windows 10/11 x64 target; onedir. Build environment:
Windows 11 10.0.26200, CPython 3.14.7 MSC v.1944 AMD64, PyInstaller 6.22.3,
hooks-contrib 2026.8, PySide6/Qt 6.11.2, PyMuPDF/MuPDF 1.28.2. Venv, build
interpreter and python314.dll agree. APP_VERSION, schema 1, backup format 1,
GUI, icon and template are unchanged.

## 3. Inventory

Pruned baseline: 328 files / 50 DLLs / 166,607,375 bytes.
Final: {files} files / {dlls} DLLs / {bytes} bytes; {native} native files.
File-count/size growth is notice/documentation material copied to both existing
license resource locations, not reintroduced runtime dependencies. No packaging
collection/exclusion or dependency versions were changed.
All 92 non-EXE natives remain byte-identical to the validated pruned payload.
The EXE's 14 common CArchive payload entries (including PYZ and main) are identical
to the validated diagnostic twin; its only extra entry is the diagnostic hook.
The formal EXE does not include that hook.

## 4. Pruning Confirmation

Qt VirtualKeyboard/plugin, Quick/QML chain, QtPdf/qpdf, PIL native/PYZ modules,
and the JDK-sourced API-set/UCRT copies remain absent. qwindows, modern Windows
style, JPEG/ICO decoding, software OpenGL and all three MuPDF natives remain.
No new pruning experiment or promotion was performed.

## 5. Application AGPL

Root LICENSE contains the complete AGPL Version 3 text, with original official
download provenance retained in licenses/GNU/README.md. AGPL-3.0-only remains
consistent in identity/README/notices. A fresh GNU download was attempted but
failed TLS/timeout; no replacement text was invented or license modified.
Local same-release source candidate: `{source_name}`, SHA-256 `{source_sha}`.
This is prepared, not uploaded or declared privacy-cleared.

## 6. Qt / Bindings

Retained QtCore, Gui, Widgets, UiTools, Network, OpenGL, OpenGLWidgets and Svg:
representative exact 6.11.2 library source headers offer LGPL-3.0-only OR
GPL-2.0-only OR GPL-3.0-only plus commercial alternative. Original headers and
attributions were inspected; 8,980 source SPDX records are saved. UiTools is
audited as its library, not all unrelated GPL tools in the QtTools archive.
No GPL-only retained library is identified by this review; this is not a blanket
license declaration for all Qt or all source-tree code.
PySide6/Shiboken6 6.11.2 exact shared source archive is acquired. Dynamic DLL
imports are recorded in the component map. Independent onedir DLL files permit
ABI-compatible replacement; no actual replacement build was tested. Nekozzz
imposes no extra reverse-engineering restriction for debugging modifications.
Remaining requirement: confirm wheel patches/configuration and compiled third-
party dependencies, then deliver the applicable sources/notices under LGPL terms.

## 7. Qt Plugins / Codecs

Retained actual directories/files are enumerated in THIRD_PARTY_NOTICES and the
component map: imageformats (9), iconengines, platforms (4), styles, generic,
networkinformation and TLS backends. Each native has source origin/hash/imports.
PNG is QtGui functionality. Exact source-tree codec versions: libjpeg-turbo 3.2.0,
libpng 1.6.58, zlib 1.3.2, TIFF 4.7.2, WebP 1.6.0. Their original notices and
additional font/text dependencies are preserved. Those versions are not claimed
as independently verified compiled wheel versions. Wheel options remain to be
reconciled. No plugin was removed in this task.

## 8. Software OpenGL

Current opengl32sw.dll SHA-256:
`34b444c016289b560662ff896deceb7f4b2c0723aed3d319ae167c9186ce42b3`.
Downloaded three official Qt historical Mesa 11.2.2 packages (unsigned, signed,
signed_sha256). Full DLL hashes differ from current binary. Eight major PE
sections (.text, .rdata, .data, .pdata, .gfids, .tls, _RDATA, .reloc) match every
reference; the resource/full-file correspondence still differs. This supports
a common code payload but does not prove complete build/patch/notice provenance.
Mesa 11.2.2/LLVM 3.6.2 strings remain supporting evidence, not sole proof.
Reference packages contain only the DLL, no complete notice/source set.
Qt wiki describes later LLVM5/Mesa17 builds, so its current recipe is not silently
applied to this older binary. Fallback kept; exact composite notices/source build
remain blocker. See `report/clearance/opengl_reference_comparison.json`.

## 9. PyMuPDF / MuPDF

Bindings/native wheel bytes match the installed distribution; runtime versions
are both 1.28.2. Exact PyMuPDF sdist acquired and its SHA matches PyPI metadata.
Its setup.py names MuPDF 1.28.2 source URL. Full MuPDF source archive acquired,
with 7,170 thirdparty members covering rendering/compression/font/XML/other
dependencies. Original COPYING/license notices have been preserved, without
declaring every source dependency compiled. Actual wheel build workflow/options,
patches and complete compiled-dependency correspondence still require verification.
Providing the application's AGPL LICENSE alone is insufficient. No recompile,
native replacement or source upload performed.

## 10. CPython

Full Python 3.14.7 source archive acquired; installed full LICENSE includes PSF,
historical and embedded notices. python314.dll/python3.dll/base_library.zip/stdlib
and extension modules are grouped by interpreter ownership. Official exact
PCbuild/get_externals.bat names libffi3.4.4, OpenSSL3.5.7, SQLite3.50.4,
zlib-ng2.2.4 and other dependencies; saved locally. Runtime zlib compatibility
version 1.3.1.zlib-ng and Expat2.8.2 were observed. Source-tree/binary external
hash correspondence is not inferred merely from version labels. No interpreter
change and no separate copyright claim over stdlib files.

## 11. OpenSSL

libssl-3.dll/libcrypto-3.dll: 3.5.7; origins and hashes match CPython DLLs.
Python _ssl/_hashlib import them; retained Qt OpenSSL TLS backend is also recorded.
Apache-2.0 license plus attribution preserved in licenses/native/OpenSSL.
Full exact official 3.5.7 source archive now acquired; original root LICENSE is
also retained under upstream_sources. Archive review finds a separate Perl
Text-Template license for build tooling, not evidence it is runtime-linked.
Earlier root NOTICE HTTP404 is not used to assert absence of all attribution
requirements. No OpenSSL DLL removed. Source reference:
https://openssl-library.org/source/license/index.html.

## 12. libffi

libffi-8.dll matches CPython DLLs and is imported by _ctypes. Official Python
3.14.7 build recipe specifies libffi3.4.4 source/binary tags. Exact binary-to-tag
hash verification remains unperformed; ABI8 alone is not version proof.
MIT permission/disclaimer and Anthony Green/Red Hat attribution are retained
verbatim in CPython LICENSE. Lack of an independently confirmed version is not
by itself a license blocker when the permission/attribution source is reliable.

## 13. SQLite

sqlite3.dll version 3.50.4; _sqlite3/runtime agree; CPython origin/hash recorded.
SQLite deliverable code is public domain, not MIT. Source/status/blessing reference
https://sqlite.org/copyright.html; no conventional copyleft source requirement.
Database schema or filenames were not altered.

## 14. lxml

lxml6.1.3: all seven installed native files match the exact official PyPI
cp314-win_amd64 wheel and its PyPI SHA digest. Runtime libxml2=2.11.9,
libxslt=1.1.45. Both runtime and compiled feature sets report iconv and zlib.
An iconv-enabled API feature does not identify GNU libiconv versus another
implementation or establish its exact version/license/linkage.
Exact lxml tag workflow instead lists libxml2=2.14.6/libxslt=1.1.43,
libiconv=1.18/zlib=1.3.2. Thus that workflow alone cannot prove this wheel's
actual dependency build. Original BSD/ElementTree/native notices are retained.
Resolve actual native source/build set and any LGPL source/relink requirements.
See lxml_wheel_comparison.json and lxml_workflow.json in report/clearance.

## 15. Other Python Dependencies

pyodbc5.3.0 MIT-0 (actual text); openpyxl3.1.5 MIT; et_xmlfile2.0.0 MIT;
pywin32 312 multi permissive/PSF/PythonWin notices retained. Actual ownership
includes win32ui/COM, not a blanket MIT mapping. Pure Python modules are mapped
from the final PYZ. Pillow12.3.0 is build/test only; excluded at runtime.
Experiment requirements: python-docx1.2.0, typing_extensions4.16.0, lxml6.1.3,
pywin32 312. The experimental-only entries are not mislabeled formal runtime.

## 16. Microsoft VC Runtime

Ten retained files: five PySide6, three Shiboken6, two Python copies. Exact file
versions, hashes and source origins are in report/clearance/vc_runtime_files.json.
MSVCP140, MSVCP140_1, MSVCP140_2, VCRUNTIME140, VCRUNTIME140_1 support the native
components. No JDK API-set/UCRT remains; system UCRT loads from System32.
Microsoft official guidance limits redistribution to licensed Visual Studio
users subject to applicable terms; its REDIST list is conditional on entitlement.
Wheel origin/signature alone is not that grant. Developer entitlement question
was requested separately; unless documented, permission remains NOT CLEARED.
No DLL removal/replacement or installer installation attempted.

References:
https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170
https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution

## 17. PyInstaller

6.22.3 bootloader/loader: GPL-2.0-or-later WITH Bootloader-exception, original
notices retained. Actual bootloader remains unmodified except ordinary packaging
resource/archive assembly. Six embedded runtime hooks each have Apache-2.0
SPDX source headers (including inspect/pkgutil/multiprocessing/pyside6), correcting
the previous generic mapping. contrib2026.8 hooks are Apache-2.0.
Build-only versions: altgraph0.17.5, packaging26.3, pefile2024.8.26,
pywin32-ctypes0.2.3, setuptools84.0.0. No collection rules changed.

## 18. Native Ownership

{native} native entries include the EXE; all have identified owner categories;
UNKNOWN native owner count is zero. File provenance is based on TOC, installed
source-byte matching, PE imports/version metadata and hashes. Known ownership
does not imply cleared composite license/source obligations. Windows system
imports are not counted as copied components. No unexpected .so was introduced.

## 19. Notices

THIRD_PARTY_NOTICES now reflects the pruned retained bundle. licenses/README.md
is the human-readable index. Original package, GNU, CPython, OpenSSL and exact
source archive texts remain unmodified. {notice_count} manifest notice entries.
Source-tree notices are conservative evidence, not assertions of runtime inclusion.
Full original notices reside in licenses rather than long quotations in the summary.

## 20. License Manifest

licenses/manifest.json records paths/hashes and runtime/build-only/supplemental
source evidence scopes. Pillow/build dependencies remain for build audit but
are not represented as runtime. Source dependencies not proven compiled are
explicitly distinguished. Collector preserves supplemental notices instead of
discarding them. All final bundled license copies match local source bytes.

## 21. Source Availability

{artifact_count} acquired upstream metadata/source/reference artifacts are recorded
with official URL, filename, bytes and SHA in report/clearance/source_artifacts.json.
Actual app candidate has {source_count} allowlisted source/resource/notice files.
SOURCE_AVAILABILITY lists executable delivery steps and unresolved correspondence;
it is not an invented public source URL or a fulfilled source offering.
Archives remain local, ignored from accidental repository staging; intended
source release artifacts must be reviewed and supplied deliberately.

## 22. Resource Provenance

Formal PNG/ICO are from developer-supplied icon(2).png; current project icon,
not a new claim of third-party ownership. Excel is developer-exported/organized
Access structure description. DOCX is developer-created, with fields/format
adapted from an unlocatable historical public tender; not copied original DOCX.
Developer adjusted alignment/row height and found no notice in comparable public
documents. No ownership over original tender format is asserted.
Excel/template/icon hashes are unchanged. Template SHA remains
892ae87bd316d82448cbd297938359417b7a08650f3d40f6c3b182a803119a52.

## 23. Privacy / Repository Hygiene

Static allowlisted Python scan: {privacy_hits} candidates, all numeric fixtures/
assertions in tests; no credential assignment/private-key/user-path rule hit.
This is not a comprehensive no-PII guarantee. Author/lastModifiedBy metadata
exists in Excel and DOCX; Company empty; Excel workbook XML contains a local
absolute path. Values are not reproduced publicly. Developer review required;
files not modified. Actual source candidate retains these original bytes.
Repository local-data inventory found 32 Images files and Access/database/backup/
settings/experimental material; none should be blindly uploaded. Only paths/counts
were inspected, no real-image content extraction. Raw generated logs may contain
local paths; newly ignored. Git is not assumed and no push/upload occurred.
Old formal directory contained DB/settings and was preserved intact, with hashes,
under build/prune_experiments/formal_previous_clearance/Nekozzz.
Final clean formal bundle has {userdata} user database/settings files.

## 24. Tests

Full tests/: {tests} passed, {failures} failures, {errors} errors, {skips} skips,
{seconds}s. Existing gc.disable isolation preserved; no skip/deletion/weakened
assertions. Earlier initial full run also passed245. Final EXE startup/first launch
PASS with Windows platform and System32-only PATH. Diagnostic twin PASS:
all navigation/About/themes/input, PNG/JPEG/ICO/missing preview, multipage PDF,
rotation/cleanup, real XLSX export/readback, AutoFill/Word attachment plans.
Proof: all92 native payloads and all14 common CArchive entries identical to final
formal EXE; only extra twin diagnostic hook. Not presented as real Word writes.
No protected GUI/business/version/resource/spec or historical-report hashes changed.

## 25. Manual QA Remaining

Actual Word COM was unavailable; existing-document Word image output and AutoFill
document writes require manual QA. No Word process was started/installed and no
fake Word test is called real COM validation. Chinese IME was manually confirmed
during pruning; this round's synthetic input is not a new real-IME verification.
Windows10/11 clean second-machine, GPU/RDP fallback and DLL replacement QA remain.
These deployment tests are separate from the license blockers.

## 26. Required Release Contents

Eventually: final onedir executable/resources; full application LICENSE;
THIRD_PARTY_NOTICES; complete applicable original component notices; readable
license manifest/index; actual corresponding-source archives and binary-source
map/checksums/patches/build recipes; documented compatible Qt replacement rights.
No production DB, Access, Images, settings, backups, raw logs or experimental outputs.
Resolve privacy metadata before uploading original resources/source candidate.
No release ZIP, installer or public upload was made in this task.

## 27. Remaining Blockers

| Blocker | Evidence | Why it matters | Exact action to clear |
|---|---|---|---|
| Software OpenGL exact composite source/notices | Official historical packages share major code sections but complete DLL/resource hashes differ; reference packages have only DLL | Cannot assert complete Mesa/LLVM/embedded redistribution notices/build correspondence | Obtain Qt/vendor record mapping this exact DLL hash/resource modification to source revisions, patches/build recipe and complete notices; reconcile and include them |
| Qt wheel configuration / compiled attribution and source set | Exact library sources/notices acquired; wheel-specific native build options not supplied | Same version/source-tree notices do not identify every incorporated dependency or fulfill LGPL source delivery | Obtain exact PySide/Shiboken/Qt wheel build records/SBOM/options/patches; map retained modules/plugins/dependencies to prepared source, add any missing corresponding artifacts/notices |
| MuPDF wheel corresponding source completeness | Exact full archives acquired, setup default matches1.28.2; actual wheel patches/options/dependency map not verified | AGPL binary conveyance needs actual corresponding source, not only application LICENSE | Verify wheel workflow/source revisions/options/patches and compiled thirdparty set against DLL; prepare required source/build set and recipient access manifest |
| lxml native dependency/source correspondence | Official wheel hashes match; runtime versions differ from exact tag workflow; iconv API feature enabled | Implementation/license/source obligations cannot be inferred from LICENSES.txt or workflow defaults | Obtain actual Windows wheel dependency build manifest; identify iconv implementation/version/linkage, native sources/options/patches and applicable LGPL source/relink materials |
| Microsoft VC redistribution entitlement | Ten wheel/Python-sourced DLLs; official REDIST terms conditional on licensed distributor | Mere file presence or signature grants no established redistribution right | Document distributor's applicable Visual Studio license/terms and exact REDIST grant/file eligibility; verify any third-party sublicense route if relied upon |

Unknown versions/provenance are not guessed. Metadata privacy review is an
additional publication hold, not a substitute for these license/source blockers.

## 28. Final Release Checklist

- [x] Preserve pruned runtime and frozen application/resource/version/spec.
- [x] Acquire exact source candidates; preserve original notice texts and hashes.
- [x] Rebuild clean onedir, inventory/map, run complete tests and packaged smoke.
- [ ] Clear each source/provenance/Microsoft blocker with recorded evidence.
- [ ] Review author/local-path metadata and confirm resource publication rights.
- [ ] Complete Word/AutoFill and clean second-PC QA without business changes.
- [ ] Verify final source artifacts match actual release binary and compliant source access.
- [ ] Only then select A/B readiness status and have developer perform publication.

No GUI/business/database/Word/PDF/AutoFill change, no pruning, no dependency/version
change, no Git commit/push, no publication. Historical audit/pruning reports preserved.
'''
    values = dict(files=counts['files'], dlls=counts['dlls'], bytes=counts['bytes'],
                  native=counts['native_or_blob'], source_name=source['artifact'], source_sha=source['sha256'],
                  source_count=len(source['files']), notice_count=len(manifest), artifact_count=len(artifacts),
                  privacy_hits=len(privacy['candidate_hits']), userdata=len(privacy['bundle_user_data_files']),
                  tests=tests['tests'], failures=tests['failures'], errors=tests['errors'], skips=tests['skips'],
                  seconds=tests['seconds'])
    assert verified['native_payload_identical'] and not verified['different_common_payloads']
    assert not verified['protected_files_changed']
    (ROOT / 'NEKOZZZ_0.9.2_FINAL_LICENSE_CLEARANCE.md').write_text(text.format(**values), encoding='utf-8')
    print('NOT READY — LICENSE BLOCKERS REMAIN; report generated')


if __name__ == '__main__':
    main()
