# Build the Windows binary: packaging/build.ps1  (run from the repo root)
# Output: dist\Utterleaf\ — windowless app entries + an explicit diagnostic CLI.
$ErrorActionPreference = 'Stop'

if (-not (Test-Path '.\.venv\Scripts\python.exe')) {
    Write-Error "Run from the repo root with a .venv present."
}

if (-not (Test-Path '.\.venv\Scripts\pyinstaller.exe')) {
    & .\.venv\Scripts\python -m pip install pyinstaller
}

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
