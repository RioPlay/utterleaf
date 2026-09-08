# Build the Windows binary: packaging/build.ps1  (run from the repo root)
# Output: dist\Utterleaf\ — windowless app entries + an explicit diagnostic CLI.
$ErrorActionPreference = 'Stop'

if (-not (Test-Path '.\.venv\Scripts\python.exe')) {
    Write-Error "Run from the repo root with a .venv present."
}

if (-not (Test-Path '.\.venv\Scripts\pyinstaller.exe')) {
    & .\.venv\Scripts\python -m pip install pyinstaller
}

# Regenerate the exe icon from the leaf renderer; the spec consumes the .ico.
& .\.venv\Scripts\python 'packaging\make_icon.py'
if ($LASTEXITCODE -ne 0) { exit 1 }

& .\.venv\Scripts\pyinstaller --noconfirm --clean 'packaging\utterleaf.spec'
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ''
Write-Host 'Built: dist\Utterleaf\'
Write-Host '  utterleaf.exe      windowless app'
Write-Host '  utterleafw.exe     windowless compatibility entry / start-at-login'
Write-Host '  utterleaf-cli.exe  diagnostic console (doctor, polish, toggle)'
Write-Host 'Sign the exes (signtool) before shipping; unsigned builds trip SmartScreen.'

# Release checksums: publish SHA256SUMS.txt next to the download so users can
# verify an unsigned build before running it.
$exeDir = 'dist\Utterleaf'
$hashes = Get-ChildItem "$exeDir\*.exe" | ForEach-Object {
    $h = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower() + '  ' + $_.Name
    "$h"
}
$hashes | Set-Content -Encoding ascii "$exeDir\SHA256SUMS.txt"
Write-Host 'SHA256SUMS.txt written.'

# Third-party license texts + notices ship inside dist\Utterleaf (legal hygiene,
# regenerated every build).
& .\.venv\Scripts\python 'packaging\collect_notices.py'
if ($LASTEXITCODE -ne 0) { exit 1 }

# The readme sits at the top of the dist folder, the first thing a user sees
# after extracting the zip.
Copy-Item 'README.md' "$exeDir\README.md"

# Distribution policy: no model weights ship in the archive. Weights download
# at first run into the user's app-data models folder, never beside the exes.
$weights = Get-ChildItem $exeDir -Recurse -File | Where-Object {
    $name = $_.Name.ToLowerInvariant()
    $name -like 'model.bin' -or $name -like '*.safetensors' -or $name -like '*.gguf'
}
if ($weights) {
    Write-Error "Model weights must not ship in dist: $($weights.FullName -join ', ')"
    exit 1
}
Write-Host 'Weight-free distribution check passed.'
