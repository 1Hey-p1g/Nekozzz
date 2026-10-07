# Nekozzz 0.9.2 Windows Portable

## Build

From the project directory, using the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build_windows.ps1
```

For a clean audited rebuild: `.\build_windows.ps1 -Clean`.
This does not change the data-directory guard or dependency pins.
The current final audit status is NOT READY — BLOCKERS REMAIN; inspect
NEKOZZZ_0.9.2_FINAL_BINARY_LICENSE_AUDIT.md before distributing the binary.

Output: `dist/Nekozzz/Nekozzz.exe`, `_internal/`, and empty `database/`,
`Images/`, `config/`, `Backups/`. Distribute the **whole directory**.
No Access sample, SQLite business database, existing Images or settings are bundled.
The spec includes immutable UI, normalized PNG, personnel Word template,
migration schema Excel, LICENSE and third-party notices.
The ICO and Windows version metadata are embedded into the executable.
Application version comes from `version.py` (0.9.2, Windows four-part 0.9.2.0).

Runtime prerequisites: Windows 10/11 x64 and a sufficient Microsoft Visual C++
v14 x64 Redistributable installed on the system. VC runtime DLLs and the
redistributable installer are not bundled; install the official Microsoft x64
Redistributable if the system lacks it. This build does not download/install it.

Formal XML processing uses the validated Python stdlib adapter. lxml is not a
runtime requirement and is excluded from the bundle. Historical experiments and
source-audit/reference environments may still intentionally use lxml; installing
requirements into an existing environment does not uninstall its old packages.
openpyxl uses its existing ElementTree/et_xmlfile backend in the no-lxml runtime.
The accepted Qt image boundary is PNG/JPEG/ICO/SVG; GIF/ICNS/TGA/TIFF/WBMP/WebP,
alternate QPA/TUIO/QtNetwork and bundled software OpenGL are not provided.

Runtime prerequisites: Windows 10/11 x64 and a sufficient Microsoft Visual C++
v14 x64 Redistributable installed on the system. VC runtime DLLs and the
redistributable installer are not bundled; install the official Microsoft x64
Redistributable if the system lacks it. This build does not download/install it.

Formal XML processing uses the validated Python stdlib adapter. lxml is not a
runtime requirement and is excluded from the bundle. Historical experiments and
source-audit/reference environments may still intentionally use lxml; installing
requirements into an existing environment does not uninstall its old packages.
openpyxl uses its existing ElementTree/et_xmlfile backend in the no-lxml runtime.
The accepted Qt image boundary is PNG/JPEG/ICO/SVG; GIF/ICNS/TGA/TIFF/WBMP/WebP,
alternate QPA/TUIO/QtNetwork and bundled software OpenGL are not provided.

## First launch

Double-click Nekozzz.exe. If `database/TenderSystem-v1.db` does not exist,
the existing V1 initializer creates a complete empty database (13 tables, schema
version 1). Existing databases are validated; invalid files show an error and
exit without deleting, rebuilding or overwriting them.
New users can start entering records immediately. Access users open Settings ->
Data management -> Access migration. While the current default DB is a validated
V1 empty database, "migrate and use as current" is available: migration validates
an independent new SQLite, checks the current empty DB again, safely replaces it,
then exits and asks for restart. If any business table has records, this option
is unavailable; migration can only create an independent new SQLite.
The old `database/tender.db` protection remains in force.
For source development, `--database <independent-v1.db>` remains required.

The only official icon source is `resources/icon.png`; Windows EXE icon is the
generated `resources/icon.ico`. No root-level temporary icon is needed.

Images, config/settings.json and Backups always belong to the EXE directory,
even if the selected SQLite is elsewhere. Keep the SQLite database and matching
Images together when preparing a portable installation. Move the full folder to
a normal writable location, never Program Files. Resources inside `_internal`
are read-only application resources, not a destination for user data.

## Theme and Windows

The Settings theme is persisted as `system`, `light`, or `dark`; old settings
default to `system`. Changes take effect immediately. Follow-system reads the
Windows AppsUseLightTheme value at startup; live OS-change watching is not
implemented. Native caption uses DWM attributes where available; normal native
dragging, resizing, system menu, snapping and caption buttons are retained.
Older Windows may ignore unsupported caption colors.

## Human acceptance

- Check window, taskbar, Alt+Tab and Explorer icon; inspect 16/24/32/48/64/128/256.
- Move, resize all four sides/corners, minimize, maximize, restore, double-click
  caption, Win+Arrow, Snap Layout, taskbar and multiple monitors/DPI if available.
- Check light/dark/system in all five modules, settings, dialogs, tables,
  scrollbars, Toast, image preview and large image viewer; restart persists theme.
- Copy the entire output to another writable directory. Use a **test V1 DB and
  test Images/settings**. Check migration to a new DB, PDF import, backup, restore,
  Excel export, and manually insert into a disposable Word document.
- Restore testing must use the isolated complete data root, not just another
  `--database` path. Success exits the application; restart to check restored data.
- Test on a second Windows PC without Python. Word insertion requires desktop
  Microsoft Word; Access migration requires a matching 64-bit Access ODBC driver.
  Neither external product/driver is included in the portable application.

Experimental personnel AutoFill is included. No schema upgrades or onefile build.

## Open-source distribution

Include LICENSE, THIRD_PARTY_NOTICES.md and licenses/ with the whole onedir folder.
The accepted runtime is frozen. Final delivery files and the remaining specific
source-companion items are recorded in NEKOZZZ_0.9.2_FINAL_RELEASE_CLEARANCE.md,
SOURCE_AVAILABILITY.md and SOURCE_DELIVERY_INDEX.json. Historical audits refer
to earlier bundles and are not the final dependency table. Do not rebuild the
accepted executable for documentation-only changes.
