[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$SessionDirectory)
$ErrorActionPreference = 'Stop'
$sessionPath = [System.IO.Path]::GetFullPath($SessionDirectory)
$manifestPath = Join-Path $sessionPath 'session.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { throw "No local demo manifest: $manifestPath" }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.session_directory -ne $sessionPath) { throw 'Session directory does not match its manifest' }
[System.IO.File]::WriteAllText((Join-Path $sessionPath 'stop.request'), 'User requested clean shutdown')
Write-Output "Shutdown requested for $sessionPath. Data and evidence are preserved."
