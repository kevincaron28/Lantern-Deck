# Build Lantern Deck for Windows x64.
#   .\build.ps1                 folder build + self-test + portable ZIP (+ installer when Inno Setup is installed)
#   .\build.ps1 -SkipInstaller  skip the installer even if Inno Setup is available
#
# Optional code signing: set LANTERN_SIGN_THUMBPRINT to a code-signing certificate in your
# certificate store (or LANTERN_SIGNTOOL_ARGS for a full custom signtool argument list, e.g.
# Azure Trusted Signing's /dlib options). Without either, the build is unsigned.
param([switch]$SkipInstaller)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$python = 'work/build-env/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    python -m venv work/build-env
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the build environment.' }
}
& $python -m pip install --disable-pip-version-check -q -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }

$version = (& $python tools/build_assets.py work).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not generate the icon and version resource.' }
Write-Output "Building Lantern Deck $version"

$dist = 'outputs/dist'
if (Test-Path -LiteralPath "$dist/Lantern Deck") { Remove-Item -Recurse -Force -LiteralPath "$dist/Lantern Deck" }
& $python -m PyInstaller --noconfirm --clean --windowed --onedir --name 'Lantern Deck' `
    --icon "$PSScriptRoot/work/lantern.ico" --version-file "$PSScriptRoot/work/version_info.txt" `
    --add-data "$PSScriptRoot/web;web" --collect-data qrcode --hidden-import pystray._win32 `
    --exclude-module tkinter `
    --distpath $dist --workpath work/pyinstaller --specpath work "$PSScriptRoot/run_lantern.py"
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }

$app = "$dist/Lantern Deck"
Copy-Item LICENSE, QUICK-START.txt, MAISON-SETUP.txt -Destination $app
Copy-Item -Recurse licenses -Destination "$app/licenses"

function Invoke-Sign([string]$file) {
    $signtool = Get-Command signtool -ErrorAction SilentlyContinue
    if (-not $signtool) {
        $kit = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue | Select-Object -Last 1
        if ($kit) { $signtool = $kit.FullName } else { $signtool = $null }
    } else { $signtool = $signtool.Source }
    if ($env:LANTERN_SIGNTOOL_ARGS -and $signtool) {
        & $signtool sign ($env:LANTERN_SIGNTOOL_ARGS -split ' ') $file
    } elseif ($env:LANTERN_SIGN_THUMBPRINT -and $signtool) {
        & $signtool sign /sha1 $env:LANTERN_SIGN_THUMBPRINT /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $file
    } else {
        Write-Output "Not signed (no certificate configured): $file"
        return
    }
    if ($LASTEXITCODE -ne 0) { throw "Signing failed: $file" }
}
Invoke-Sign "$app/Lantern Deck.exe"

& $python tests/smoke_bundle.py
if ($LASTEXITCODE -ne 0) { throw 'Packaged self-test failed.' }

$zip = "outputs/Lantern-Deck-$version-Portable.zip"
if (Test-Path -LiteralPath $zip) { Remove-Item -Force -LiteralPath $zip }
Compress-Archive -Path $app -DestinationPath $zip
$artifacts = @($zip)

$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($SkipInstaller) {
    Write-Output 'Installer skipped.'
} elseif ($iscc) {
    & $iscc /Q "/DVersion=$version" installer/LanternDeck.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
    $setup = "outputs/Lantern-Deck-$version-Setup.exe"
    Invoke-Sign $setup
    $artifacts += $setup
} else {
    Write-Output 'Inno Setup 6 not found: installer skipped (portable ZIP still built). Install it from jrsoftware.org to build Setup.exe.'
}

$sums = foreach ($file in $artifacts) { "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash.ToLower(), (Split-Path -Leaf $file) }
$sums | Set-Content -Encoding ascii "outputs/SHA256SUMS-$version.txt"
Write-Output "Done:"; $artifacts | ForEach-Object { Write-Output "  $_" }
