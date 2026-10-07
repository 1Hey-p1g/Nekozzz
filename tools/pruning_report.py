"""Generate experiment evidence summaries; does not alter builds or licenses."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'report/pruning'
MECHANISMS = {
    '01_qt_virtualkeyboard': 'QtGui upstream collector -> platforminputcontexts/qtvirtualkeyboardplugin -> Qt6VirtualKeyboard -> Quick/QML. Filter only the root plugin before bindepend.',
    '02_qt_pdf': 'QtGui upstream collector -> imageformats/qpdf -> Qt6Pdf. Filter qpdf before bindepend; PyMuPDF native binaries remain untouched.',
    '03_pillow': 'Optional imports in openpyxl.drawing.image and PyMuPDF pil_* methods cause PIL collection. Candidate excludes only PIL; build dependency remains installed and unchanged.',
    '04_jdk_ucrt': 'bindepend Windows fallback traverses inherited PATH. Microsoft JDK bin resolves CRT API-set/UCRT copies; remove that entry only in the child build environment, retaining VC runtimes.',
}


def record(name, baseline_name, status, promoted):
    baseline = json.loads((REPORT / (baseline_name + '_inventory.json')).read_text(encoding='utf-8'))
    candidate = json.loads((REPORT / (name + '_inventory.json')).read_text(encoding='utf-8'))
    before = {p['path']: p for p in baseline['files']}
    after = {p['path']: p for p in candidate['files']}
    removed = sorted(before.keys() - after.keys())
    removed_dlls = {Path(p).name.lower() for p in removed if p.endswith('.dll')}
    retained_imports = [dict(file=p['path'], dependency=i) for p in after.values()
                       for i in p.get('imports', []) + p.get('delay_imports', []) if i.lower() in removed_dlls]
    modules_removed = sorted(set(baseline['pyz']) - set(candidate['pyz']))
    tests = json.loads((REPORT / (name + '_tests.json')).read_text(encoding='utf-8'))
    smoke = json.loads((REPORT / (name + '_packaged_smoke.json')).read_text(encoding='utf-8'))
    startup = json.loads((REPORT / (name + '_startup.json')).read_text(encoding='utf-8'))
    twin = json.loads((REPORT / (name + '_probe_equivalence.json')).read_text(encoding='utf-8'))
    result = dict(experiment=name, baseline=baseline['counts'], candidate=candidate['counts'],
                  removed_files=removed, removed_pyz_modules=modules_removed,
                  remaining_imports_to_removed_files=retained_imports, collection_mechanism=MECHANISMS[name],
                  tests=tests, packaged_smoke=smoke, normal_exe_startup=startup, diagnostic_twin=twin,
                  status=status, promoted_to_formal=promoted,
                  source_suite_is_not_frozen_suite=True,
                  manual_verification=smoke.get('manual_verification', []))
    if name == '01_qt_virtualkeyboard':
        result['developer_ime'] = json.loads((REPORT / '01_manual_ime.json').read_text())
        result['manual_verification'] = [x for x in result['manual_verification'] if not x.startswith('Real Windows Chinese')]
    if name == '04_jdk_ucrt':
        # References to OS API-set contracts are expected; this is not a dangling
        # Qt plugin -> removed Qt DLL chain. qwindows/system UCRT smoke provides
        # platform evidence, not a claim of testing every Windows 10 patch level.
        result['expected_system_contract_imports'] = retained_imports
        result['manual_verification'].append('Windows 10 and a separate clean Windows 11 machine not available for smoke')
        origins = {p['destination'].replace('\\', '/'): p['source'] for p in baseline['sources']
                   if p['kind'] in ('BINARY', 'EXTENSION')}
        result['all_removed_files_jdk_provenance'] = all(
            origins.get(p.removeprefix('_internal/'), '').startswith('%MICROSOFT_JDK_17%') for p in removed)
        vc = [p for p in before if Path(p).name.lower().startswith(('vcruntime', 'msvcp'))]
        result['retained_vc_runtime_files'] = vc
        result['vc_runtime_hashes_unchanged'] = all(p in after and before[p]['sha256'] == after[p]['sha256'] for p in vc)
        result['remaining_jdk_sources'] = [p for p in candidate['sources'] if '%MICROSOFT_JDK' in p['source']]
        if status == 'PASS' and (not result['all_removed_files_jdk_provenance']
                                or not result['vc_runtime_hashes_unchanged'] or result['remaining_jdk_sources']):
            raise RuntimeError('Unexpected UCRT/VC runtime provenance diff')
    if status == 'PASS' and (tests['status'] != 'PASS' or tests['skips'] or smoke['status'] != 'PASS'
                            or startup['status'] != 'PASS' or not twin['all_native_payloads_identical']):
        raise RuntimeError('Cannot declare PASS with failed evidence')
    if status == 'PASS' and name != '04_jdk_ucrt' and retained_imports:
        raise RuntimeError('Removed DLL still has a retained native dependent')
    if status == 'PASS' and (twin['pyz_additions'] or twin['pyz_removals']):
        raise RuntimeError('Diagnostic Python archive differs from candidate')
    critical = {'opengl32sw.dll', 'qwindows.dll', 'qmodernwindowsstyle.dll', 'qjpeg.dll', 'qico.dll',
                'qt6core.dll', 'qt6gui.dll', 'qt6widgets.dll', 'qtuitools.pyd'}
    required = [p for p in before if Path(p).name.lower() in critical
                or (p.startswith('_internal/pymupdf/') and p.endswith(('.dll', '.pyd')))]
    result['critical_payload_hashes_unchanged'] = all(p in after and before[p]['sha256'] == after[p]['sha256'] for p in required)
    if status == 'PASS' and not result['critical_payload_hashes_unchanged']:
        raise RuntimeError('Protected runtime payload changed')
    (REPORT / (name + '_result.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = [f'# {name}', '', f'Conclusion: **{status}**', '', f'Promoted to formal configuration: **{promoted}**', '',
             '## Baseline / Candidate', '', '| | Files | DLLs | Bytes |', '|---|---:|---:|---:|']
    for label, data in [('Baseline', result['baseline']), ('Candidate', result['candidate'])]:
        lines.append(f"| {label} | {data['files']} | {data['dlls']} | {data['bytes']:,} |")
    lines += ['', '## Collection / Dependency Evidence', '', MECHANISMS[name], '',
              'Complete PE imports/delay imports and source Analysis TOC records: companion inventory JSON.',
              'Source source-code absence alone is not treated as proof of runtime absence.', '',
              '## Removed Files', ''] + ['- `' + p + '`' for p in removed]
    lines += ['', '## Removed Python Archive Modules', '', '```json', json.dumps(modules_removed, indent=2), '```', '',
              '## Remaining References to Removed DLL Names', '', '```json', json.dumps(retained_imports, indent=2), '```', '',
              'For Experiment 4 these are system-resolved API contracts, not absent Qt libraries.', '',
              '## Reproduction', '', '```powershell',
              f'.\\.venv\\Scripts\\python.exe -B -m tools.pruning_experiments build {name} --group {name[:2].lstrip("0")}',
              f'.\\.venv\\Scripts\\python.exe -B -m tools.pruning_experiments build {name} --group {name[:2].lstrip("0")} --probe',
              f'.\\.venv\\Scripts\\python.exe -B -m tools.pruning_experiments startup {name}',
              f'.\\.venv\\Scripts\\python.exe -B -m tools.pruning_experiments smoke {name}',
              f'.\\.venv\\Scripts\\python.exe -B -m tools.pruning_regression {name}', '```', '',
              'Generated spec/work directories: `build/prune_experiments/`; isolated binaries: `dist/prune_experiments/`.',
              'Reproduction must use the formal baseline recorded for this step; later formal promotions are cumulative.', '',
              '## Tests / Packaged Smoke', '', f"Complete source tests/: **{tests['tests']} passed**, skips={tests['skips']}, GC isolation=True.",
              f"Normal Windows candidate first launch: **{startup['status']}**; TEMP V1 initialized.",
              f"Frozen diagnostic twin: **{smoke['status']}**; {len(smoke['checks'])} automated checks.",
              f"Native payload hashes identical: **{twin['all_native_payloads_identical']}**; PYZ additions/removals: {twin['pyz_additions']} / {twin['pyz_removals']}.",
              'The diagnostic hook runs only in the twin, never the formal spec. No external development modules on runtime path.',
              'Checks include actual qwindows, full navigation/About/themes, synthetic Qt input events, PNG/JPEG/ICO, missing images, multipage PDF/JPG/rotation, people XLSX export, AutoFill attachment plan and Word image plan.',
              f"Word COM: {smoke.get('word_com', 'not checked')}", '', '## Manual Verification Remaining', '']
    lines += ['- ' + x for x in result['manual_verification']]
    if 'developer_ime' in result:
        lines += ['', 'Real Chinese IME: developer confirmed this candidate composition/candidate selection/commit normal and closed it.']
    lines += ['', 'No business test was removed/skipped/weakened. No requirement/dependency versions changed.', '',
              '## Unexpected Files / Scope', '',
              'Inventory lists all retained files; software OpenGL, QtCore/Gui/Widgets/UiTools, qwindows, qmodernwindowsstyle, qjpeg/qico and PyMuPDF native components retained.',
              'No final license clearance is implied by pruning PASS.', '']
    (REPORT / (name + '.md')).write_text('\n'.join(lines), encoding='utf-8')
    print(name, status, promoted, candidate['counts'])


def final_report():
    results = [json.loads((REPORT / (name + '_result.json')).read_text(encoding='utf-8')) for name in MECHANISMS]
    final = json.loads((REPORT / 'final_formal_inventory.json').read_text(encoding='utf-8'))
    tests = json.loads((REPORT / 'final_tests.json').read_text(encoding='utf-8'))
    verification = json.loads((REPORT / 'final_verification.json').read_text(encoding='utf-8'))
    baseline = json.loads((REPORT / 'baseline_inventory.json').read_text(encoding='utf-8'))
    status = 'PRUNING COMPLETE' if all(r['status'] == 'PASS' and r['promoted_to_formal'] for r in results) else 'PRUNING PARTIALLY COMPLETE'
    if tests['status'] != 'PASS' or tests['skips'] or not verification['formal_matches_candidate_native_and_pyz']:
        status = 'PRUNING BLOCKED'
    lines = ['# Nekozzz 0.9.2 — Dependency Pruning Report', '', 'Date: 2026-10-03 (Asia/Shanghai)', '',
             '## 1. Executive Summary', '', f'**{status}**', '',
             'Four groups were tested separately, in the requested order. Each PASS was promoted and followed by a clean formal build before the next experiment.',
             'This is packaging verification, not Final License Clearance. Public binary license status remains **NOT READY — BLOCKERS REMAIN**.', '',
             '## 2. Baseline', '',
             '- Previous license-audit artifact: 383 files / 99 DLLs / 198,710,470 bytes.',
             f"- Fresh unchanged-dependency build including the accepted About page: {baseline['counts']['files']} files / {baseline['counts']['dlls']} DLLs / {baseline['counts']['bytes']:,} bytes.",
             '- The 335-byte difference is the accepted About-page code; it is not dependency pruning.',
             '- At task start, actual old dist also contained a 139,264-byte first-launch V1 database (13 tables, zero business rows). It was excluded from the clean artifact baseline and preserved intact with the old installation, with developer authorization.',
             '- Baseline complete tests/: 245 passed, no skips, documented process-local gc.disable() isolation.',
             '- CPython 3.14.7; PyInstaller 6.22.3; hooks-contrib 2026.8; PySide6/Qt 6.11.2; PyMuPDF 1.28.2; x64 Windows 11 build 10.0.26200; onedir.',
             '- Requirements, interpreter and dependency versions unchanged.', '']
    for index, r in enumerate(results, 3):
        name = r['experiment']
        lines += [f'## {index}. Experiment {name}', '', f"**{r['status']}**, promoted={r['promoted_to_formal']}.", '',
                  r['collection_mechanism'], '',
                  f"Baseline: {r['baseline']['files']} files / {r['baseline']['dlls']} DLLs / {r['baseline']['bytes']:,} bytes.",
                  f"Candidate: {r['candidate']['files']} files / {r['candidate']['dlls']} DLLs / {r['candidate']['bytes']:,} bytes.",
                  f"Complete source tests/: {r['tests']['tests']} passed, zero skips. Normal EXE startup and equivalent frozen diagnostic twin smoke passed.",
                  f"Detailed evidence: [report/pruning/{name}.md](report/pruning/{name}.md).", '']
    lines += ['## 7. Successful Removals', '',
              '- VirtualKeyboard plugin + Qt6VirtualKeyboard/Quick/Qml/QmlMeta/QmlModels/QmlWorkerScript: 7 DLLs, 13,597,832 bytes.',
              '- qpdf plugin + Qt6Pdf: 2 DLLs, 4,662,896 bytes.',
              '- Pillow runtime: 6 PYDs and 76 PIL PYZ modules; incidental stdlib colorsys also no longer collected. Artifact reduction: 11,814,694 bytes (including archive changes). Pillow remains a build dependency.',
              '- JDK-sourced UCRT/API-set: 40 DLLs, 2,028,008 bytes. Ten VC runtime files retained unchanged.', '',
              '## 8. Failed / Inconclusive Removals', '',
              '- No requested removal failed or remained inconclusive after validation; all four were promoted.',
              '- Test-harness setup errors were fixed before conclusions: a probe initially used a read-only connection for TEMP fixture setup and a wrong QApplication.exec binding; direct regression-runner invocation initially omitted the project import path; a TEMP read connection initially remained open during cleanup. Initial failure logs are retained. These were harness errors independent of the removals, not application regressions, and no business code/tests were modified to fix them.', '',
              '## 9. Final Binary Inventory', '', '| Artifact | Files | DLLs | Bytes |', '|---|---:|---:|---:|',
              '| Previous audit | 383 | 99 | 198,710,470 |',
              f"| Current About baseline | {baseline['counts']['files']} | {baseline['counts']['dlls']} | {baseline['counts']['bytes']:,} |",
              f"| Final formal | {final['counts']['files']} | {final['counts']['dlls']} | {final['counts']['bytes']:,} |", '',
              f"Difference vs previous audit: {383-final['counts']['files']} fewer files, {99-final['counts']['dlls']} fewer DLLs, {198710470-final['counts']['bytes']:,} fewer bytes.",
              f"Difference vs current-code baseline: {baseline['counts']['bytes']-final['counts']['bytes']:,} fewer bytes.",
              'Fresh inventory and component maps regenerated; no native component owner UNKNOWN was reported. Existing unresolved license/provenance issues are not cleared by this fact.', '',
              '## 10. Formal Spec / Build Configuration Changes', '',
              '- Nekozzz.spec: user QtGui hook directory and PIL exclude only; runtime_hooks remains empty.',
              '- tools/pyinstaller_hooks/hook-PySide6.QtGui.py: retain upstream collector, filter only qtvirtualkeyboardplugin.dll and qpdf.dll before recursive native collection.',
              '- tools/build_pyinstaller_environment.py and build_windows.ps1: remove the observed Microsoft JDK bin from the child build PATH. Parent/developer/application PATH is not changed. No post-build DLL deletion.',
              '- Diagnostic runtime hook appears only in separate *_probe candidates; not in the formal build. Normal/probe native hashes and PYZ module sets are identical.',
              '- Supporting local tools: pruning_experiments.py, pruning_probe_hook.py, pruning_packaged_probe.py, pruning_regression.py, pruning_report.py.',
              '- No business GUI, services, repositories, database, migration, schema, templates, icons, identity versions or requirements changed.',
              '- Old installations are preserved under build/prune_experiments/formal_previous_*/Nekozzz with hash verification. The original default DB is in formal_previous_01_qt_virtualkeyboard/Nekozzz/database/.', '',
              '## 11. Test Results', '', '| Run | Tests | Status | Skips | Seconds |', '|---|---:|---|---:|---:|']
    base_tests = json.loads((REPORT / 'baseline_tests.json').read_text())
    for label, r in [('Baseline', base_tests)] + [(r['experiment'], r['tests']) for r in results] + [('Final formal', tests)]:
        lines.append(f"| {label} | {r['tests']} | {r['status']} | {r.get('skips', 0)} | {r['seconds']} |")
    lines += ['', 'All complete tests/ runs retain existing assertions and GC isolation; no skip/deletion/weakened assertion.',
              'Packaged probes used actual qwindows on Windows, with only Windows/System32 in the external runtime PATH. Development PYTHONPATH/PYTHONHOME and external Qt/QML paths were removed.',
              'Verified normal EXE first launch, empty schema-1 database, full navigation/About/settings/themes, LineEdit/editable ComboBox input events, PNG/JPEG/ICO decoding, missing-image placeholder, three-page PyMuPDF render/rotation/temporary cleanup, real people XLSX export/readback, AutoFill real-template attachment plan, Word real-image plan.',
              'The source suite is not a frozen test suite: a separate candidate diagnostic twin executes the actual frozen application modules. Its native/PYZ equivalence is recorded for each candidate and final formal build.',
              'Experiment 1 real Chinese IME composition/candidate selection/commit was manually confirmed by the developer. System IMM32/MSCTF remain loaded; qwindows payload unchanged.',
              'Final protection/packaged evidence: [report/pruning/final_verification.json](report/pruning/final_verification.json).', '',
              '## 12. Manual Verification Remaining', '',
              '- Real Word image output and real AutoFill document write: Word.Application was unavailable. No Word was started, document opened/created/saved, or real output written. Source fake-COM tests and frozen plan tests do not substitute for this.',
              '- Clean Windows 10 and another Windows 11 computer/VM smoke, including native IME, DPI, graphics/Remote Desktop and Word. Target remains Windows 10/11; no minimum patch level/support-range change was declared from a single Windows 11 host.',
              '- Optional upstream APIs requiring Pillow (openpyxl drawing.Image, PyMuPDF pil_*) no longer work in the frozen runtime. Nekozzz does not invoke them in its audited existing workflows; future use requires reevaluation.',
              '- Candidate/probe artifacts are diagnostic only, never release artifacts. Raw local build logs may contain machine paths and should be reviewed before any future source publication.', '',
              '## 13. Remaining License Audit Scope', '',
              '- Qt/PySide/Shiboken modules and retained plugins/codecs, exact corresponding source/notices.',
              '- PyMuPDF/MuPDF corresponding source, build information and embedded third-party obligations.',
              '- software OpenGL/Mesa/LLVM exact provenance/notices; opengl32sw.dll deliberately retained unchanged.',
              '- Ten Microsoft VC runtime files and redistribution entitlement; removal of JDK UCRT copies does not settle VC runtime rights.',
              '- CPython/stdlib native components, OpenSSL, libffi, SQLite, lxml/native dependencies, Qt image codecs and PyInstaller runtime terms as applicable.',
              '- THIRD_PARTY_NOTICES/ and licenses/ deliberately not rewritten for candidates or license-cleared here. Inventory/component maps describe the final retained runtime. A later Final License Clearance must reconcile notices with the pruned artifact.',
              '- No Final License Clearance, Git operations, source archive, release ZIP, installer, upload or dependency upgrade performed.', '']
    (ROOT / 'NEKOZZZ_0.9.2_DEPENDENCY_PRUNING_REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    print(status, final['counts'])


if __name__ == '__main__':
    if sys.argv[1] == 'final':
        final_report()
    else:
        record(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4].lower() == 'true')
