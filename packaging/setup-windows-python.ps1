# GitHub Actions: use the same Python.org runtime ZIP as the native notice review.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'notices\runtime-manifest.json') -Raw | ConvertFrom-Json
$version = $manifest.python_version
$sha256 = $manifest.python_windows_x64_archive_sha256
if ($version -notmatch '^3\.[0-9]+\.[0-9]+$' -or $sha256 -notmatch '^[0-9a-f]{64}$') {
    throw 'Invalid reviewed Windows Python archive metadata.'
}

$work = Join-Path $env:RUNNER_TEMP "utterleaf-python-$([guid]::NewGuid())"
New-Item -ItemType Directory -Path $work | Out-Null
$archive = Join-Path $work 'python.zip'
$runtime = Join-Path $work 'runtime'
Invoke-WebRequest -UseBasicParsing -Uri "https://www.python.org/ftp/python/$version/python-$version-amd64.zip" -OutFile $archive
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $sha256) {
    throw 'Downloaded Windows Python archive does not match the reviewed SHA-256.'
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($archive, $runtime)
$runtime | Out-File -FilePath $env:GITHUB_PATH -Encoding utf8 -Append
