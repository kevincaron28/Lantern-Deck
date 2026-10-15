$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath 'work/build-env/Scripts/python.exe')) {
    python -m venv work/build-env
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the build environment.' }
}
& 'work/build-env/Scripts/python.exe' -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }
& 'work/build-env/Scripts/python.exe' -m PyInstaller --noconfirm --windowed --onefile --name 'Lantern Deck' --add-data "$PSScriptRoot/web;web" --collect-data qrcode --distpath outputs --workpath work/pyinstaller --specpath work "$PSScriptRoot/launcher.py"
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
Write-Output 'Built outputs/Lantern Deck.exe'
