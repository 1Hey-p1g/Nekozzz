param([switch]$Clean)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    # Never let a repeat build erase portable data someone put into dist.
    foreach ($folder in 'database', 'Images', 'config', 'Backups') {
        $dataFolder = Join-Path 'dist\Nekozzz' $folder
        if ((Test-Path -LiteralPath $dataFolder) -and
            (Get-ChildItem -LiteralPath $dataFolder -File -Recurse | Select-Object -First 1)) {
            throw "Release output contains user data in $dataFolder; move the whole installation before rebuilding."
        }
    }
    & '.\.venv\Scripts\python.exe' -B -c "from PIL import Image; im=Image.open('resources/icon.png'); im.save('resources/icon.ico', sizes=[(s,s) for s in (16,24,32,48,64,128,256)]); im.close()"
    if ($LASTEXITCODE -ne 0) { throw 'ICO generation failed' }
    $buildArguments = @('-B', '-m', 'PyInstaller', '--noconfirm')
    if ($Clean) { $buildArguments += '--clean' }
    & '.\.venv\Scripts\python.exe' -B 'tools\build_pyinstaller_environment.py' @buildArguments Nekozzz.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
    foreach ($folder in 'database', 'Images', 'config', 'Backups') {
        New-Item -ItemType Directory -Force -Path (Join-Path 'dist\Nekozzz' $folder) | Out-Null
    }
    foreach ($notice in 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'SOURCE_AVAILABILITY.md') {
        Copy-Item -LiteralPath $notice -Destination (Join-Path 'dist\Nekozzz' $notice)
    }
    Copy-Item -LiteralPath 'licenses' -Destination 'dist\Nekozzz\licenses' -Recurse -Force
    Copy-Item -LiteralPath 'BUILD_WINDOWS.md' -Destination 'dist\Nekozzz\README.md'
} finally { Pop-Location }
