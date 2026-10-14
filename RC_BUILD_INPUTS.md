# Nekozzz 0.9.4 RC1 source snapshot

This is a local SHA256-bound snapshot, not a Git tag or public release. The
development directory has no Git metadata. APP_VERSION=0.9.4, schema=1, backup=1.

Use Windows x64 Python 3.14.7 and pinned requirements-build.txt. PyInstaller
6.22.3, onedir spec and supplied ICO are unchanged. Do not regenerate the template.
Microsoft Visual C++ v14 x64 Runtime is an external system prerequisite.

In a clean build environment, with unrelated JDK directories removed from the
build subprocess PATH (they can introduce unrelated UCRT DLLs):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -B tools/build_pyinstaller_environment.py -B -m PyInstaller --clean --noconfirm --workpath build/rc-work --distpath dist/rc Nekozzz.spec
```

Original source documentation remains a historical build-input snapshot.
README_RC.md, RC_SOURCE_MAP.json and the 0.9.4 report describe this candidate.
All third-party DLL/PYD hashes match the previous 0.9.3 distribution. The unchanged
source-companion ZIP is reused byte-for-byte, preserving its historical evidence.

Run only tests/, using the existing test-process GC isolation procedure and
temporary SettingsService paths. Never run root historical test scripts on user data.
Access tests need a separately authorized local fixture. No business ACCDB, private
database or Images content is supplied; the 294-test run used local test fixtures.
