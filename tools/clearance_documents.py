"""Generate evidence-backed source delivery records; no publishing or pruning."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'report/clearance'


def main():
    records = {}
    for name in ('report/clearance_sources/manifest.json', 'report/clearance/additional_sources.json',
                 'report/clearance/opengl_download.json', 'report/clearance/opengl_other_downloads.json',
                 'report/clearance/openssl_source.json'):
        value = json.loads((ROOT / name).read_text(encoding='utf-8'))
        for row in value if isinstance(value, list) else [value]:
            if 'filename' not in row:
                continue
            path = ROOT / 'report/clearance_sources' / row['filename']
            if path.is_file():
                records[row['filename']] = dict(row, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                                bytes=path.stat().st_size,
                                                status='ACQUIRED; correspondence status separately recorded')
    (OUT / 'source_artifacts.json').write_text(json.dumps(list(records.values()), indent=2), encoding='utf-8')
    lines = ['# Nekozzz 0.9.2 — source delivery preparation', '',
             '**NOT READY — LICENSE BLOCKERS REMAIN.** Archives below exist locally;',
             'they have not been published and are not all verified corresponding source.', '',
             '## Prepared upstream artifacts', '',
             'Local directory: `report/clearance_sources/`. Metadata-only PyPI JSON is evidence,',
             'not a source archive. SHA-256 is locally computed; PyMuPDF/lxml sdists also',
             'match the digests in exact-version PyPI metadata. See `report/clearance/source_artifacts.json`.', '',
             '| Filename | Bytes | SHA-256 | Official source |', '|---|---:|---|---|']
    for row in records.values():
        lines.append(f"| {row['filename']} | {row['bytes']} | `{row['sha256']}` | {row['url']} |")
    lines += ['', '## Binary correspondence / outstanding work', '',
              '- CPython 3.14.7: acquired full source; actual interpreter/python314.dll and build recipe agree.',
              '  PCbuild names external source/binary tags. Reconcile external library hashes/notices as recorded.',
              '- Qt 6.11.2: qtbase supplies Core/Gui/Widgets/Network/OpenGL/OpenGLWidgets; qttools supplies',
              '  UiTools; qtsvg supplies Svg; qtimageformats supplies additional codecs. Original module licenses',
              '  and attribution files have been preserved. Confirm exact wheel patches/options/compiled dependencies.',
              '- PySide/Shiboken 6.11.2: acquired exact shared source distribution and build scripts;',
              '  matching version is not a complete wheel build-provenance record.',
              '- PyMuPDF 1.28.2: exact sdist setup.py specifies MuPDF 1.28.2 archive. Full MuPDF archive includes',
              '  its thirdparty tree. Supply/verify actual wheel workflow, patches, configuration and dependency mapping.',
              '- Software OpenGL: acquired three Qt historical binary references. Eight major non-resource PE',
              '  sections match current DLL, but full file hashes differ. Exact build/patches/composite notices unresolved.',
              '- lxml 6.1.3: exact sdist acquired. Runtime libxml2/libxslt versions are known; native wheel linkage,',
              '  including possible LGPL iconv, requires provenance/source reconciliation.', '',
              '## Application source candidate', '',
              '`Nekozzz-0.9.2-source-candidate.zip` is prepared locally by',
              '`tools/prepare_clearance_source.py`. Its companion manifest contains the archive SHA-256 and',
              'every included file hash. It uses an explicit allowlist, excludes user databases/Images/Access data/',
              'settings/backups/build artifacts/raw logs, and includes the current build recipe and dependency pins.',
              'It preserves the supplied Excel/template bytes. Their nonempty author metadata and the Excel local',
              'path need developer privacy review before uploading. No metadata has been removed or altered.', '',
              '## Executable release delivery checklist', '',
              '1. Resolve every source/provenance/rights blocker in the final clearance report.',
              '2. Verify the application candidate against the final build and confirm privacy/resource distribution.',
              '3. Complete native wheel source/build/dependency records; include all applicable patches and notices.',
              '4. Keep immutable archive filenames, versions, hashes, build recipes and the exact binary-to-source map.',
              '5. Make applicable corresponding source available alongside the same-version binary, using the selected',
              '   AGPL/GPL/LGPL conveyance method. Publish stable links only after the real release location exists.',
              '6. Test downloading the actual corresponding-source artifacts as a recipient; do not link a moving latest branch.', '',
              'These are actual prepared artifacts plus explicit unfinished requirements, not a future-download promise.',
              'The current set is **not a fulfilled corresponding-source offering**. No GitHub URL or legal entitlement',
              'is invented, and no files have been uploaded.']
    (ROOT / 'SOURCE_AVAILABILITY.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Recorded', len(records), 'acquired upstream artifacts')


if __name__ == '__main__':
    main()
